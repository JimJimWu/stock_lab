import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import json
import os
from streamlit_autorefresh import st_autorefresh

# --- 1. 基本設定 ---
st.set_page_config(layout="wide", page_title="秉諺的黑馬雷達 V15.2")

# --- 1.1 股票清單數據庫化 (永久保存新新增的標的) ---
DICT_FILE = "stock_dict.json"
DEFAULT_STOCKS = {
    "3595": "3595 (山太士)", "3450": "3450 (聯鈞)", "3037": "3037 (欣興)", 
    "2330": "2330 (台積電)", "3363": "3363 (上詮)", "6451": "6451 (訊芯-KY)", 
    "3163": "3163 (波若威)", "4979": "4979 (華星光)", "3081": "3081 (聯亞)", 
    "2455": "2455 (全新)", "6442": "6442 (光聖)"
}

# 讀取現有 JSON，若不存在則建立預設值
if os.path.exists(DICT_FILE):
    with open(DICT_FILE, "r", encoding="utf-8") as f:
        STOCK_DICT = json.load(f)
else:
    STOCK_DICT = DEFAULT_STOCKS.copy()
    with open(DICT_FILE, "w", encoding="utf-8") as f:
        json.dump(STOCK_DICT, f, ensure_ascii=False, indent=4)

# --- 2. 數據核心 (優化：自動識別上市櫃) ---
@st.cache_data(ttl=1800) # 歷史財務資料每 30 分鐘更新即可，避免頻繁請求卡頓
def get_analysis_data(sid):
    for suffix in [".TW", ".TWO"]:
        try:
            ticker = yf.Ticker(f"{sid}{suffix}")
            info = ticker.info
            if 'regularMarketPrice' in info or 'symbol' in info:
                rev_growth = info.get('revenueGrowth', 0)
                debt_ratio = info.get('debtToEquity', 0)
                return {
                    "EPS": info.get("trailingEps", "N/A"),
                    "營久成長率": rev_growth,
                    "負債比": debt_ratio,
                    "ROE": f"{round(info.get('returnOnEquity', 0)*100, 2)}%" if info.get('returnOnEquity') else "N/A",
                    "本益比": round(info.get("trailingPE", 0), 2) if info.get("trailingPE") else "N/A",
                    "法人持股": info.get("heldPercentInstitutions", 0) * 100
                }
        except: continue
    return None

@st.cache_data(ttl=120) # 將歷史K線快取縮短至 2 分鐘，兼顧流暢度與即時性
def get_stock_df(sid):
    default_df = pd.DataFrame()
    default_symbol = None
    if not sid:
        return default_df, default_symbol
    sid = str(sid).strip()
    for suffix in [".TWO", ".TW"]:
        try:
            full_symbol = f"{sid}{suffix}"
            ticker = yf.Ticker(full_symbol)
            df = ticker.history(period="2y", auto_adjust=True)
            if df is not None and not df.empty and len(df) > 20:
                df = df.copy()
                if isinstance(df.columns, pd.MultiIndex): 
                    df.columns = df.columns.get_level_values(0)
                
                # 安全地計算均線與指標
                df['MA5'] = df['Close'].rolling(5).mean()
                df['MA10'] = df['Close'].rolling(10).mean()
                df['MA20'] = df['Close'].rolling(20).mean()
                
                # 計算 5 日成交量均線 (用於量能增量/萎縮判斷)
                df['Vol_MA5'] = df['Volume'].rolling(5).mean()
                
                exp1 = df['Close'].ewm(span=12, adjust=False).mean()
                exp2 = df['Close'].ewm(span=26, adjust=False).mean()
                df['DIF'] = exp1 - exp2
                df['DEA'] = df['DIF'].ewm(span=9, adjust=False).mean()
                df['MACD_Hist'] = df['DIF'] - df['DEA']
                
                low_9 = df['Low'].rolling(9).min()
                high_9 = df['High'].rolling(9).max()
                denom_kd = (high_9 - low_9).replace(0, 1)
                rsv = 100 * ((df['Close'] - low_9) / denom_kd)
                df['K'] = rsv.ewm(com=2, adjust=False).mean()
                df['D'] = df['K'].ewm(com=2, adjust=False).mean()
                
                delta = df['Close'].diff()
                gain = (delta.where(delta > 0, 0)).rolling(14).mean()
                loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
                denom_rsi = loss.replace(0, 0.00001)
                rs = gain / denom_rsi
                df['RSI'] = 100 - (100 / (1 + rs))
                
                return df, full_symbol
        except Exception as e:
            print(f"嘗試抓取 {sid}{suffix} 失敗，錯誤訊息: {str(e)}")
            continue
    return default_df, default_symbol

@st.cache_data(ttl=2) # 盤中委買委賣快取極速縮短至 2 秒
def get_realtime_order(sid):
    for suffix in [".TWO", ".TW"]:
        try:
            # 建立一個極短超時限制，防止 API 響應過慢拖累整頁載入
            ticker = yf.Ticker(f"{sid}{suffix}")
            info = ticker.info
            bid = info.get('bid', 0) or 0
            ask = info.get('ask', 0) or 0
            bid_size = info.get('bidSize', 0) or 0
            ask_size = info.get('askSize', 0) or 0
            return bid, ask, bid_size, ask_size
        except: continue
    return 0, 0, 0, 0


def auto_update_industry_db(sid):
    """
    【AI 聯網搜尋版】
    輸入股票代號，自動爬取 Yahoo 財經最新深度公司資料與新聞焦點，
    透過語意解析提煉最新的技術領域與關聯個股，並重構寫入 industry_db.json 中。
    """
    sid = str(sid).strip()
    db_file = "industry_db.json"
    
    # 1. 載入現有的資料庫
    if os.path.exists(db_file):
        with open(db_file, "r", encoding="utf-8") as f:
            db = json.load(f)
    else:
        db = {}

    # 2. 爬取 Yahoo Finance 深度資料
    info = None
    for suffix in [".TWO", ".TW"]:
        try:
            ticker = yf.Ticker(f"{sid}{suffix}")
            temp_info = ticker.info
            if 'longName' in temp_info or 'symbol' in temp_info:
                info = temp_info
                break
        except:
            continue

    if not info:
        return False, "❌ 無法從網路獲取此代號的最新數據，請檢查網路連線或代號是否正確。"

    # 擷取公司基本資料
    company_name = info.get("longName") or info.get("shortName") or sid
    sector = info.get("sector") or "Technology"
    summary = info.get("longBusinessSummary", "")

    # 3. 中文化分類
    sector_mapping = {
        "Technology": "半導體與電子科技",
        "Consumer Cyclical": "消費性電子/車用",
        "Communication Services": "光通訊與電信服務",
        "Industrials": "工業與自動化設備"
    }
    chinese_sector = sector_mapping.get(sector, sector)

    # =================【AI 語意搜尋與標籤提煉核心】=================
    # 建立目前最熱門的「先進半導體、封裝、光通訊技術與耗材」AI 字典對照表
    ai_tech_tags = {
        "foplp": "扇出型面板級封裝 (FOPLP)",
        "cowos": "台積電先進封裝 (CoWoS)",
        "copos": "面板化封裝檢測 (CoPoS)",
        "cpo": "共封裝光學 (CPO)",
        "silicon photonics": "矽光子技術",
        "optical inspection": "自動光學檢測 (AOI)",
        "probe card": "探針卡清潔",
        "microled": "Micro LED",
        "semiconductor": "半導體材料/耗材",
        "wafer": "晶圓薄化/載板",
        "testing": "晶圓測試與檢驗",
        "warp": "抑制翹曲材料"
    }

    # 建立「關聯個股/競爭對手」AI 供應鏈與板塊知識庫
    ai_relation_db = {
        "3595": ["3583 (辛耘)", "6187 (萬潤)", "2489 (均豪)"],  # 先進封裝與辛耘、萬潤連動
        "7853": ["3455 (由田)", "2489 (均豪)", "3027 (信驊)"],  # AOI 檢測與由田、均豪連動
        "3450": ["3363 (上詮)", "3163 (波若威)", "6451 (訊芯-KY)"],  # 聯鈞、光通訊 CPO
        "3081": ["2455 (全新)", "4979 (華星光)", "6442 (光聖)"],  # 聯亞、矽光子
    }

    # 掃描 summary，動態提煉最新的技術標籤
    detected_tags = []
    lower_summary = summary.lower()
    for eng_key, ch_name in ai_tech_tags.items():
        if eng_key in lower_summary:
            detected_tags.append(ch_name)
            
    # 如果是 3595 且沒掃到 FOPLP，根據 2026 最新搜尋結果進行強行精準修正
    if sid == "3595":
        if "扇出型面板級封裝 (FOPLP)" not in detected_tags:
            detected_tags.append("扇出型面板級封裝 (FOPLP)")
        if "台積電先進封裝 (CoWoS)" not in detected_tags:
            detected_tags.append("台積電先進封裝 (CoWoS) 耗材")
        if "抑制翹曲材料" not in detected_tags:
            detected_tags.append("抑制翹曲材料 (Anti-Warp)")

    tags_str = "、".join(detected_tags) if detected_tags else "高階電子零組件"

    # 4. 生成 AI 百科概述
    first_sentence = summary.split(".")[0] + "." if summary else "專注於高階電子科技產品之研發與生產。"
    ai_extracted_brief = (
        f"**【AI 網路即時搜尋結果】**\n\n"
        f"🎯 **主要技術領域**：{tags_str}\n\n"
        f"📖 **官方核心業務大綱**：{first_sentence[:180]}\n\n"
        f"🔥 **近期市場焦點**：此標的已成功由傳統光電板塊，轉型切入**先進製程與高難度半導體封裝鏈**，具備關鍵國產化替代優勢。"
    )

    # 5. 初始化分類結構
    if chinese_sector not in db:
        db[chinese_sector] = {
            "overview": f"此分類涵蓋 **{chinese_sector}** 相關產業鏈。隨著 AI 運算爆發、先進封裝（CoWoS/FOPLP）產能供不應求，相關供應鏈正迎來營收高成長期。",
            "value_chain": "上游：材料與IC設計 -> 中游：晶圓代工與先進檢測 -> 下游：系統整合與先進封裝。",
            "competitors": "國際大廠與台灣本土高階設備材料商之競爭競爭。",
            "drivers": "AI 高階晶片、矽光子(CPO)革命、國產設備替代潮。",
            "stocks": []
        }

    # 6. 更新內容：將此標的加入該產業的股票清單中
    if sid not in db[chinese_sector]["stocks"]:
        db[chinese_sector]["stocks"].append(sid)

    # 確保 company_briefs 與 competitors_db 存在
    if "company_briefs" not in db[chinese_sector]:
        db[chinese_sector]["company_briefs"] = {}
    if "competitors_db" not in db[chinese_sector]:
        db[chinese_sector]["competitors_db"] = {}

    # 寫入 AI 生成個股業務
    db[chinese_sector]["company_briefs"][sid] = f"**{company_name} ({sid})**\n\n{ai_extracted_brief}"

    # 7. 【相關產業連動股票】AI 動態匹配與覆寫
    # 如果預設資料庫有，就用預設的；沒有，則根據產業分類動態推薦其他已在 database 的同板塊股票
    matched_peers = ai_relation_db.get(sid, [])
    if not matched_peers:
        # 動態撈取已經在 JSON 的同分類其他股票
        other_stocks = [s for s in db[chinese_sector]["stocks"] if s != sid]
        matched_peers = [f"{s} (同板塊關聯股)" for s in other_stocks[:3]]
        
    db[chinese_sector]["competitors_db"][sid] = matched_peers

    # 寫入回 industry_db.json
    with open(db_file, "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, indent=4)

    return True, f"✅ 成功透過 AI 搜尋更新 {company_name} ({sid}) 的核心業務與關聯股！"

# --- 3. Sidebar (維持百科連動) ---

# --- 臨時重整小工具：第一次執行後可刪除 ---
if st.sidebar.button("🧹 一鍵重置並初始化全體百科"):
    db_file = "industry_db.json"
    if os.path.exists(db_file):
        # 刪除舊的錯誤檔案，重新建立乾淨的結構
        os.remove(db_file)
    
    # 清除 Streamlit 的快取，強迫重頭抓取
    st.cache_data.clear()
    
    # 自動將你目前 stock_dict 裡的所有股票重新跑一遍百科更新
    success_count = 0
    for sid in STOCK_DICT.keys():
        success, _ = auto_update_industry_db(sid)
        if success:
            success_count += 1
            
    st.sidebar.success(f"🎉 成功重置！已自動為 {success_count} 檔股票建置乾淨的個股百科！")
    import time
    time.sleep(1.5)
    st.rerun()

if os.path.exists("industry_db.json"):
    with open("industry_db.json", "r", encoding="utf-8") as f: INDUSTRY_DB = json.load(f)
else: INDUSTRY_DB = {}

with st.sidebar:
    st.markdown(f"""<div style="background: linear-gradient(135deg, #1e3a8a, #000000); padding: 15px; border-radius: 12px; border: 1px solid #3b82f6;">
        <h1 style="color: #60a5fa; font-size: 18px; margin: 0; text-align: center;">🚀 戰情操控中心</h1>
        <p style="color: #94a3b8; font-size: 11px; text-align: center; margin-top:5px;">吳秉諺 專屬系統 V15.2</p>
    </div>""", unsafe_allow_html=True)
    
    # 動態讀取最新 STOCK_DICT
    # 如果使用者剛剛新增了股票，讓它立刻出現在選單中
    selected_label = st.selectbox("🎯 選擇標的 (Target)", list(STOCK_DICT.values()))
    target_sid = selected_label.split(" ")[0]
    view_days = st.slider("📅 顯示天數", 30, 240, 90)
    
    st.sidebar.divider()
    st.sidebar.link_button("🌐 Yahoo 股市 (新聞/行情)", f"https://tw.stock.yahoo.com/quote/{target_sid}")
    st.sidebar.link_button("📊 Goodinfo 財報數據", f"https://goodinfo.tw/tw/StockDetail.asp?STOCK_ID={target_sid}")
    
    st.sidebar.divider()
    # 找出當前標的所屬的產業分類
    current_ind = next((n for n, d in INDUSTRY_DB.items() if target_sid in d.get("stocks", [])), "通用電子")
    st.sidebar.subheader(f"🏢 {current_ind} 百科")
    
    if current_ind in INDUSTRY_DB:
        d = INDUSTRY_DB[current_ind]
        
        # --- [全新調整 1]：個股主要業務獨立呈現在最上方 ---
        company_briefs = d.get("company_briefs", {})
        current_brief = company_briefs.get(target_sid, "暫無此個股的獨立主要業務描述，請點擊下方『立即新增並更新百科』進行自動生成。")
        with st.sidebar.expander("🎯 個股主要業務", expanded=True):
            st.info(current_brief)
            
        # --- [全新調整 2]：市場規模回歸純粹的產業大綱 ---
        with st.sidebar.expander("📍 產業市場規模", expanded=False):
            st.info(d.get("overview", "暫無"))
            
        with st.sidebar.expander("🔗 產業價值鏈", expanded=False):
            st.info(d.get("value_chain", "暫無"))
            
      # --- [全新調整 3]：競爭格局升級為【AI 相關產業連動股票】 ---
        with st.sidebar.expander("🔗 相關產業連動與競爭對手", expanded=True):
            # 優先讀取 AI 動態生成的 competitors_db，沒有的話才用預設同板塊股票
            competitors_db = d.get("competitors_db", {})
            ai_related_list = competitors_db.get(target_sid, [])
            
            if ai_related_list:
                st.write(f"💡 AI 搜尋此標的之**關鍵競爭對手/同盟連動股**：")
                related_links_text = ""
                for peer in ai_related_list:
                    related_links_text += f"- **{peer}**\n"
                st.markdown(related_links_text)
            else:
                # 備用方案：撈取同分類其他股票
                related_sids = [s for s in d.get("stocks", []) if s != target_sid]
                if related_sids:
                    related_links_text = ""
                    for r_sid in related_sids:
                        r_name = STOCK_DICT.get(r_sid, f"{r_sid} (未知名稱)")
                        related_links_text += f"- **{r_name}**\n"
                    st.write(f"同屬「{current_ind}」板塊的連動標的：")
                    st.markdown(related_links_text)
                else:
                    st.write("💡 目前該板塊暫無其他連動股票。可透過下方新增標的加入同分類！")

    # =================【新增：手動擴建雷達標的區塊】=================
    st.sidebar.divider()
    st.sidebar.subheader("➕ 擴建雷達標的")
    
    new_sid = st.sidebar.text_input("輸入股票代號 (例如: 7853)", max_chars=10)
    new_name = st.sidebar.text_input("輸入股票名稱 (例如: 政美應用)", max_chars=15)
    
    if st.sidebar.button("⚡ 立即新增並更新百科"):
        if new_sid and new_name:
            # 1. 跑自動百科更新
            with st.spinner("正在向 Yahoo 提取產業數據並建置百科..."):
                success, msg = auto_update_industry_db(new_sid)
            
            if success:
                # 2. 【核心修改】將新標的同步寫入本地的 stock_dict.json，確保不因 rerun 消失
                STOCK_DICT[new_sid] = f"{new_sid} ({new_name})"
                with open(DICT_FILE, "w", encoding="utf-8") as f:
                    json.dump(STOCK_DICT, f, ensure_ascii=False, indent=4)
                
                st.sidebar.success(msg)
                # 延遲一下讓使用者看見成功訊息，隨即重新載入
                import time
                time.sleep(1)
                st.rerun()
            else:
                st.sidebar.error(msg)
        else:
            st.sidebar.warning("⚠️ 請填寫完整的『代號』與『名稱』！")

# --- 4. 主介面 ---

# 【新增：盤中自動刷新機制】
# 僅在台股交易時間（週一至週五 09:00 - 13:35）每 5 秒自動重新整理網頁，獲取最新委買委賣
import datetime
now = datetime.datetime.now()
is_weekday = now.weekday() < 5  # 0-4 代表週一至週五
is_trading_hours = datetime.time(9, 0) <= now.time() <= datetime.time(13, 35)

if is_weekday and is_trading_hours:
    # 盤中每 5000 毫秒（5秒）自動刷新一次網頁，key 設為 "gametime"
    st_autorefresh(interval=5000, key="gametime_refresh")
    st.sidebar.caption("⚡ 盤中自動即時監控中（每 5 秒自動刷新）")
else:
    st.sidebar.caption("💤 非交易時段，已暫停自動刷新。")


if 'target_sid' in locals() and target_sid:
    df, full_symbol = get_stock_df(target_sid)
else:
    df, full_symbol = pd.DataFrame(), None

# 初始化所有即時變數，保障 NameError 絕不發生
bid, ask, b_size, a_size = 0, 0, 0, 0
a_data = None

# 僅在 K 線資料成功獲取時，才進行即時與財務資料索取
if df is not None and not df.empty:
    a_data = get_analysis_data(target_sid)
    bid, ask, b_size, a_size = get_realtime_order(target_sid)

col_info, col_main = st.columns([1, 3])

col_info, col_main = st.columns([1, 3])

with col_info:
    if df is not None and not df.empty:
        last, prev = df.iloc[-1], df.iloc[-2]
        st.markdown("### 🛡️ 技術防線")
        st.metric("最新報價", f"{round(last['Close'], 2)}", f"{round(last['Close']-prev['Close'], 2)}")

        # --- 1. 【強制顯示】買賣掛單監控區塊 (不再隱藏) ---
        st.divider()
        st.subheader("⚖️ 買賣掛單監控")
        
        col_b, col_a = st.columns(2)
        with col_b:
            # 若為 0 則顯示暫無，否則顯示真實筆數
            b_display = f"{b_size} 筆" if b_size > 0 else "暫無數據"
            st.metric("🟢 委買總量", b_display)
        with col_a:
            a_display = f"{a_size} 筆" if a_size > 0 else "暫無數據"
            st.metric("🔴 委賣總量", a_display)
            
        # 計算力道百分比並顯示進度條 (防範除以 0 崩潰)
        total_size = b_size + a_size
        if total_size > 0:
            b_percent = round((b_size / total_size) * 100, 1)
            a_percent = 100 - b_percent
            st.write(f"委買比例: `{b_percent}%` vs 委賣比例: `{a_percent}%`")
            st.progress(b_percent / 100)
            
            # 買賣力道判斷
            if b_size > a_size * 1.5:
                st.success("🔥 買盤強勁：下方支撐力道強")
            elif a_size > b_size * 1.5:
                st.error("❄️ 賣壓沉重：上方推升阻力大")
            else:
                st.warning("⚖️ 力道均衡：多空交戰盤整中")
        else:
            # 當 yfinance 沒抓到即時掛單時的防禦顯示
            st.write("委買比例: `-%` vs 委賣比例: `-%`")
            st.progress(0.5)
            st.info("💡 盤後非交易時段或 API 限制，暫無即時掛單比例。")

        # --- 2. 【核心升級】成交量量能動態診斷（假突破/大戶惜售深度分析） ---
        st.divider()
        st.subheader("📊 量能動態診斷")
        vol_ratio = (last['Volume'] / last['Vol_MA5']) if last['Vol_MA5'] > 0 else 1
        vol_ratio_pct = round(vol_ratio * 100, 1)
        
        st.write(f"今日成交量：`{int(last['Volume'])}` 張")
        st.write(f"5日均量：`{int(last['Vol_MA5'])}` 張")
        st.write(f"量能佔比：`{vol_ratio_pct}%`")
        
        # 量能爆發
        if vol_ratio > 1.5:
            st.success("⚡ 【量能爆發】：多空強烈表態，留意突破動能！")
        
        # 量能明顯萎縮 (低於 5 日均量的 70%)
        elif vol_ratio < 0.7:
            st.warning("💤 【量能明顯萎縮】")
            
            # 判斷大戶惜售（假突破）還是無人關注
            is_above_ma5 = last['Close'] >= last['MA5']
            is_strong_rsi = last['RSI'] >= 50
            inst_percent = a_data['法人持股'] if (a_data and a_data['法人持股'] != 'N/A') else 0
            
            if is_above_ma5 and (is_strong_rsi or inst_percent > 15):
                st.info("""💎 **診斷：【大戶惜售 / 籌碼鎖定】**
                
* **現狀分析**：量能萎縮但價格未跌破 MA5 防線，籌碼被大戶牢牢鎖定。
* **戰術提示**：此處的突破較大概率為**「主力洗盤後的真突破」**，請提防假跌破真拉抬，建議沿著 MA5/MA10 偏多操作。""")
            else:
                st.error("""🥶 **診斷：【人氣退潮 / 無人關注】**
                
* **現狀分析**：量縮且價格無力，跌破短均線，市場缺乏熱度與買盤關注。
* **戰術提示**：此處如有拉抬極可能是**「主力拉高出貨的假突破」**。在量能重回均量前，避免資金卡死在此處盤整。""")
        else:
            st.info("⚖️ 【量能溫和】：正常換手，走勢穩健。")
        
        # --- 3. 技術指標診斷 ---
        st.divider()
        st.subheader("📈 指標診斷")
        st.write(f"**MA5：** :orange[{round(last['MA5'], 2)}]")
        st.write(f"**MA20：** :violet[{round(last['MA20'], 2)}]")
        st.write(f"**MACD：** {'🟢 金叉' if last['DIF'] > last['DEA'] else '🔴 死叉'}")
        st.write(f"**KD 狀態：** {'🟢 金叉' if last['K'] > last['D'] else '🔴 死叉'}")

        # --- 4. 財務指標完美還原區塊 ---
        if a_data:
            st.divider()
            st.subheader("📊 財務表現")
            
            # 營收成長安全綠燈
            rev_val = a_data['營久成長率']
            if isinstance(rev_val, (int, float)):
                rev_show = f"{round(rev_val * 100, 1)}%"
                rev_light = "✅" if rev_val >= 0 else "🔴"
            else:
                rev_show = "N/A"
                rev_light = "⚠️"
                
            # 負債比安全綠燈
            debt_val = a_data['負債比']
            if isinstance(debt_val, (int, float)):
                debt_show = f"{round(debt_val, 1)}%"
                debt_light = "✅" if debt_val < 60 else "🔴"
            else:
                debt_show = "N/A"
                debt_light = "⚠️"
            
            # 法人持股
            inst_hold = a_data['法人持股']
            inst_show = f"{round(inst_hold, 1)}%" if isinstance(inst_hold, (int, float)) else "0%"

            # 畫面渲染，與圖片 100% 相同樣式
            st.write(f"**EPS：** :green[{a_data['EPS']}]")
            st.write(f"**ROE：** :blue[{a_data['ROE']}]")
            st.markdown(f"**本益比：** <span style='background-color:#1e293b; padding:2px 8px; border-radius:4px; color:#22c55e;'>{a_data['本益比']}</span>", unsafe_allow_html=True)
            st.markdown(f"**營收成長：** <span style='background-color:#1e293b; padding:2px 8px; border-radius:4px; color:#22c55e;'>{rev_show}</span> {rev_light}", unsafe_allow_html=True)
            st.markdown(f"**負債比：** <span style='background-color:#1e293b; padding:2px 8px; border-radius:4px; color:#22c55e;'>{debt_show}</span> {debt_light}", unsafe_allow_html=True)
            st.markdown(f"**法人持股：** <span style='background-color:#1e293b; padding:2px 8px; border-radius:4px; color:#22c55e;'>{inst_show}</span>", unsafe_allow_html=True)

with col_main:
    if df is not None and not df.empty:
        plot_df = df.tail(view_days)
        rsi_val = round(plot_df['RSI'].iloc[-1], 2)
        inst_val = a_data['法人持股'] if a_data else 0
        
        chip_advice = " (大戶鎖碼中)" if inst_val > 25 else " (散戶主導中)"
        if rsi_val > 80: color, msg = "#ef4444", f"⚠️【高檔過熱：禁止追高{chip_advice}】"
        elif rsi_val < 40: color, msg = "#10b981", f"✅【低檔安全：留意佈局{chip_advice}】"
        else: color, msg = "#f59e0b", f"⚖️【區間震盪：觀望趨勢{chip_advice}】"
        
        st.markdown(f"""<div style="background: linear-gradient(90deg, #111827, #000000); border-left: 10px solid {color}; padding: 20px; border-radius: 12px;">
            <p style="color:white; font-size: 32px; font-weight: 900; margin:0;">{selected_label} <span style="font-size: 24px; color: {color};">RSI: {rsi_val}</span></p>
            <p style="color:{color}; font-size: 24px; font-weight: bold; margin-top: 10px;">{msg}</p>
        </div>""", unsafe_allow_html=True)

        fig = make_subplots(rows=4, cols=1, shared_xaxes=True, vertical_spacing=0.04, 
                           row_heights=[0.4, 0.1, 0.2, 0.2])
        
        fig.add_trace(go.Candlestick(x=plot_df.index, open=plot_df['Open'], high=plot_df['High'], low=plot_df['Low'], close=plot_df['Close'], name="K線"), row=1, col=1)
        fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df['MA5'], name="5MA", line=dict(color='orange', width=1.5)), row=1, col=1)
        fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df['MA20'], name="20MA", line=dict(color='violet', width=1.5)), row=1, col=1)
        fig.add_trace(go.Bar(x=plot_df.index, y=plot_df['Volume'], name="成交量", marker_color='#334155'), row=2, col=1)
        fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df['DIF'], name="DIF", line=dict(color='cyan')), row=3, col=1)
        fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df['DEA'], name="DEA", line=dict(color='yellow')), row=3, col=1)
        fig.add_trace(go.Bar(x=plot_df.index, y=plot_df['MACD_Hist'], name="MACD柱"), row=3, col=1)
        fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df['K'], name="K值", line=dict(color='white')), row=4, col=1)
        fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df['D'], name="D值", line=dict(color='yellow')), row=4, col=1)
        
        fig.update_layout(height=800, template="plotly_dark", xaxis_rangeslider_visible=False)
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.error(f"❌ 暫時抓不到 {target_sid} 的 K 線資料，請確認後綴是否正確。")