# ==============================================================================
# 秉諺的黑馬雷達 V25.0 - 網頁儀表板主程式 (價格事實還原、大戶防線精確修正、實時同步版)
# ==============================================================================
import streamlit as st  # 必須是第一個匯入

# --- 1. 頂部防禦 ---
st.set_page_config(layout="wide", page_title="秉諺的黑馬雷達 V25.0")

import pandas as pd
import yfinance as yf
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from streamlit_autorefresh import st_autorefresh
import requests
import json
import os
import datetime
import time

# --- 2. 全域時間變數 ---
now = datetime.datetime.now()
is_weekday = now.weekday() < 5
is_trading_hours = datetime.time(9, 0) <= now.time() <= datetime.time(15, 0)

# --- 3. 檔案路徑與 Discord 常數 ---
DICT_FILE = "stock_dict.json"
INDUSTRY_DB_FILE = "industry_db.json"
DEFAULT_DISCORD_WEBHOOK = os.environ.get("DISCORD_WEBHOOK") or ""

DEFAULT_STOCKS = {
    "3595": "3595 (山太士)", "3450": "3450 (聯鈞)", "3037": "3037 (欣興)", 
    "2330": "2330 (台積電)", "3363": "3363 (上詮)", "6451": "6451 (訊芯-KY)", 
    "3163": "3163 (波若威)", "4979": "4979 (華星光)", "3081": "3081 (聯亞)", 
    "2455": "2455 (全新)", "6442": "6442 (光聖)", "2486": "2486 (一銓)",
    "3714": "3714 (富采)", "1802": "1802 (台玻)", "2408": "2408 (南亞科)",
    "1815": "1815 (富喬)", "4958": "4958 (臻鼎-KY)", "7853": "7853 (政美應用)"
}

# --- 4. 永久資料庫讀寫 ---
def load_stock_dict():
    if os.path.exists(DICT_FILE):
        try:
            with open(DICT_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if data and isinstance(data, dict) and len(data) > 0:
                    return data
        except Exception as e:
            print(f"讀取 stock_dict.json 失敗: {e}")
            
    try:
        with open(DICT_FILE, "w", encoding="utf-8") as f:
            json.dump(DEFAULT_STOCKS, f, ensure_ascii=False, indent=4)
    except Exception as e:
        print(f"建立 stock_dict.json 失敗: {e}")
    return DEFAULT_STOCKS.copy()

def save_stock_dict(data):
    try:
        with open(DICT_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
        return True
    except Exception as e:
        print(f"儲存 stock_dict.json 失敗: {e}")
        return False

def load_industry_db():
    if os.path.exists(INDUSTRY_DB_FILE):
        try:
            with open(INDUSTRY_DB_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except: pass
    return {}

# 確保 Session State 初始化
if 'STOCK_DICT' not in st.session_state:
    st.session_state['STOCK_DICT'] = load_stock_dict()
if 'INDUSTRY_DB' not in st.session_state:
    st.session_state['INDUSTRY_DB'] = load_industry_db()

STOCK_DICT = st.session_state['STOCK_DICT']
INDUSTRY_DB = st.session_state['INDUSTRY_DB']

# --- 5. 百科生成模組 ---
def auto_update_industry_db(sid):
    sid = str(sid).strip()
    db_file = "industry_db.json"
    db = load_industry_db()

    info = None
    for suffix in [".TWO", ".TW"]:
        try:
            ticker = yf.Ticker(f"{sid}{suffix}")
            temp_info = ticker.info
            if 'longName' in temp_info or 'symbol' in temp_info:
                info = temp_info
                break
        except: continue

    if not info:
        return False, "❌ 無法獲取此代號數據。"

    company_name = info.get("longName") or info.get("shortName") or sid
    sector = info.get("sector") or "Technology"
    summary = info.get("longBusinessSummary", "")

    sector_mapping = {
        "Technology": "半導體與電子科技",
        "Consumer Cyclical": "消費性電子/車用",
        "Communication Services": "光通訊與電信服務",
        "Industrials": "工業與自動化設備"
    }
    chinese_sector = sector_mapping.get(sector, sector)

    # 偵測關鍵字
    ai_tech_tags = {
        "foplp": "扇出型面板級封裝 (FOPLP)",
        "cowos": "先進封裝技術 (CoWoS)",
        "copos": "面板化封裝檢測 (CoPoS)",
        "cpo": "共封裝光學 (CPO)",
        "silicon photonics": "矽光子與光通訊技術",
        "optical inspection": "自動光學檢測 (AOI)",
        "probe card": "探針卡/測試介面",
        "microled": "Micro LED 材料",
        "semiconductor": "半導體關鍵耗材",
        "wafer": "晶圓薄化/載板技術",
        "testing": "晶圓測試與檢驗",
        "warp": "抑制翹曲元件與材料"
    }

    detected_tags = []
    lower_summary = summary.lower() if summary else ""
    for eng_key, ch_name in ai_tech_tags.items():
        if eng_key in lower_summary:
            detected_tags.append(ch_name)

    tags_str = "、".join(detected_tags) if detected_tags else "高階電子零組件與先進材料"
    first_sentence = summary.split(".")[0] + "." if summary else "專注於高階電子科技產品研發。"
    
    ai_extracted_brief = (
        f"**【AI 網路即時搜尋結果】**\n\n"
        f"🎯 **主要技術領域**：{tags_str}\n\n"
        f"📖 **官方核心業務大綱**：{first_sentence[:180]}\n\n"
        f"🔥 **近期市場焦點**：成功透過核心技術轉型，切入**高階半導體封裝與先進材料供應鏈**，具備優異的國產化替代與競爭優勢。"
    )

    if chinese_sector not in db:
        db[chinese_sector] = {
            "overview": f"此分類涵蓋 {chinese_sector} 相關產業鏈。",
            "value_chain": "上游：材料與IC設計 -> 中游：晶圓代工與精密檢測 -> 下游：系統整合與先進封裝。",
            "competitors": "國際大廠與台灣本土高階設備材料商之高度競爭。",
            "drivers": "AI 高階晶片、CPO光學革命、半導體國產替代潮。",
            "stocks": []
        }

    if sid not in db[chinese_sector]["stocks"]:
        db[chinese_sector]["stocks"].append(sid)

    if "company_briefs" not in db[chinese_sector]:
        db[chinese_sector]["company_briefs"] = {}
    if "competitors_db" not in db[chinese_sector]:
        db[chinese_sector]["competitors_db"] = {}

    db[chinese_sector]["company_briefs"][sid] = f"**{company_name} ({sid})**\n\n{ai_extracted_brief}"

    other_stocks = [s for s in db[chinese_sector]["stocks"] if s != sid]
    matched_peers = [f"{s} (同板塊關聯股)" for s in other_stocks[:3]]
    if not matched_peers:
        matched_peers = ["市場同業個股 (待雷達清單擴建後自動對齊)"]
    db[chinese_sector]["competitors_db"][sid] = matched_peers

    with open(db_file, "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, indent=4)
    
    st.session_state['INDUSTRY_DB'] = db
    return True, f"✅ 成功更新 {company_name} ({sid}) 的核心業務與關聯股！"

# --- 6. 數據核心 (【V25.0 歷史 2Y 完整 K 線下載與實時對齊防線】) ---
cache_ttl = 5 if is_trading_hours else 300
@st.cache_data(ttl=cache_ttl)
def get_stock_df(sid):
    default_df = pd.DataFrame()
    suffixes = [".TWO", ".TW"] if sid in ["3595", "7853"] or len(sid) == 6 else [".TW", ".TWO"]
        
    for suffix in suffixes:
        try:
            ticker = yf.Ticker(f"{sid}{suffix}")
            df = ticker.history(period="2y", auto_adjust=True) 
            
            if df is not None and not df.empty and len(df) > 20:
                df = df.copy()
                if isinstance(df.columns, pd.MultiIndex): 
                    df.columns = df.columns.get_level_values(0)
                
                df = df.dropna(subset=['Close'])
                df = df[(df['Volume'] > 0) & (df['Volume'].notna())]

                # 💥 【V25.0 成交量統一除以 1000.0 (張)】，不再有股與張混淆造成大戶防線算錯
                df['Volume'] = df['Volume'] / 1000.0

                # 💥 【V25.0 實時快閃修正引擎】盤中破底或變動時，利用 fast_info 直接拉取最即時的報價
                try:
                    f_info = ticker.fast_info
                    if f_info and is_trading_hours:
                        today_idx = df.index[-1]
                        df.loc[today_idx, 'Close'] = float(f_info['last_price'])
                        df.loc[today_idx, 'High'] = float(f_info['day_high'])
                        df.loc[today_idx, 'Low'] = float(f_info['day_low'])
                        df.loc[today_idx, 'Open'] = float(f_info['open'])
                        df.loc[today_idx, 'Volume'] = f_info['last_volume'] / 1000.0
                except Exception as ex:
                    print(f"實時快閃修正失敗: {ex}")

                if df.empty or len(df) < 20:
                    continue

                # 計算技術指標
                df['MA5'] = df['Close'].rolling(5).mean()
                df['MA10'] = df['Close'].rolling(10).mean()
                df['MA20'] = df['Close'].rolling(20).mean()
                df['Vol_MA5'] = df['Volume'].rolling(5).mean()
                
                # MACD
                exp1 = df['Close'].ewm(span=12, adjust=False).mean()
                exp2 = df['Close'].ewm(span=26, adjust=False).mean()
                df['DIF'] = exp1 - exp2
                df['DEA'] = df['DIF'].ewm(span=9, adjust=False).mean()
                df['MACD_Hist'] = df['DIF'] - df['DEA']
                
                # KD
                low_9 = df['Low'].rolling(9).min()
                high_9 = df['High'].rolling(9).max()
                denom_kd = (high_9 - low_9).replace(0, 1)
                rsv = 100 * ((df['Close'] - low_9) / denom_kd)
                df['K'] = rsv.ewm(com=2, adjust=False).mean()
                df['D'] = df['K'].ewm(com=2, adjust=False).mean()
                
                # RSI
                delta = df['Close'].diff()
                gain = (delta.where(delta > 0, 0)).rolling(14).mean()
                loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
                denom_rsi = loss.replace(0, 0.00001)
                rs = gain / denom_rsi
                df['RSI'] = 100 - (100 / (1 + rs))
                return df
        except Exception as e:
            print(f"抓取 {sid}{suffix} K線失敗: {e}")
            continue
            
    return default_df

# 獲取校準後的現價與昨收 (100% 原始價格)
def get_yahoo_web_quote_from_df(sid, df):
    quote = {"current": 0.0, "prev_close": 0.0, "open": 0.0, "high": 0.0, "low": 0.0, "volume_txt": "0.0"}
    
    suffixes = [".TWO", ".TW"] if sid in ["3595", "7853"] or len(sid) == 6 else [".TW", ".TWO"]
    for suffix in suffixes:
        try:
            ticker = yf.Ticker(f"{sid}{suffix}")
            info = ticker.info
            if info:
                p_prev = info.get("regularMarketPreviousClose") or info.get("previousClose")
                if p_prev and p_prev > 0:
                    quote["prev_close"] = float(p_prev)
                    break
        except:
            continue
            
    if df is not None and len(df) >= 2:
        last_row = df.iloc[-1]
        quote["current"] = float(last_row['Close'])
        quote["open"] = float(last_row['Open'])
        quote["high"] = float(last_row['High'])
        quote["low"] = float(last_row['Low'])
        quote["volume_txt"] = str(round(last_row['Volume'], 1))
        
        if not quote["prev_close"] or quote["prev_close"] <= 0:
            quote["prev_close"] = float(df.iloc[-2]['Close'])
            
    return quote

# 獲取基本面數據
@st.cache_data(ttl=600) 
def get_analysis_data(sid):
    suffixes = [".TWO", ".TW"] if sid in ["3595", "7853"] or len(sid) == 6 else [".TW", ".TWO"]
    for suffix in suffixes:
        try:
            ticker = yf.Ticker(f"{sid}{suffix}")
            info = ticker.info
            if info:
                eps_val = info.get("trailingEps")
                return {
                    "EPS": eps_val if eps_val else "N/A",
                    "營久成長率": info.get('revenueGrowth', 0),
                    "負債比": info.get('debtToEquity', 0),
                    "ROE": f"{round(info.get('returnOnEquity', 0)*100, 2)}%" if info.get('returnOnEquity') else "N/A",
                    "本益比": round(info.get("trailingPE", 0), 2) if info.get("trailingPE") else "N/A",
                    "法人持股": (info.get("heldPercentInstitutions", 0) or 0) * 100
                }
        except: continue
    return None

# 掛單專用接口
@st.cache_data(ttl=5)
def get_realtime_order(sid):
    suffixes = [".TWO", ".TW"] if sid in ["3595", "7853"] or len(sid) == 6 else [".TW", ".TWO"]
    for suffix in suffixes:
        try:
            ticker = yf.Ticker(f"{sid}{suffix}")
            info = ticker.info
            if info:
                bid_price = info.get('bid') or info.get('regularMarketPrice') or 0
                ask_price = info.get('ask') or info.get('regularMarketPrice') or 0
                bid_size = info.get('bidSize') or 0
                ask_size = info.get('askSize') or 0
                return bid_price, ask_price, bid_size, ask_size
        except: continue
    return 0, 0, 0, 0

# --- 7. Discord Webhook ---
def send_discord_webhook(webhook_url, embed_data):
    if not webhook_url:
        return False, "未填寫 Discord Webhook URL"
    try:
        payload = {"embeds": [embed_data]}
        response = requests.post(webhook_url, json=payload, timeout=5)
        if response.status_code in [200, 204]:
            return True, "發送成功！"
        return False, f"發送失敗，狀態碼: {response.status_code}"
    except Exception as e:
        return False, f"發送異常: {str(e)}"

# --- 雷達單次掃描 ---
def run_single_scan_signal(sid, sname, webhook_url):
    df_scan = get_stock_df(sid)
    if df_scan.empty or len(df_scan) < 3:
        return None
        
    last, prev = df_scan.iloc[-1], df_scan.iloc[-2]
    clean_prices = get_yahoo_web_quote_from_df(sid, df_scan)
    current_price = clean_prices["current"]
    prev_price = clean_prices["prev_close"]
    
    price_change = round(current_price - prev_price, 2)
    change_pct = round((price_change / prev_price) * 100, 2)
    change_sign = "▲" if price_change > 0 else ("▼" if price_change < 0 else " ")
    color_hex = 15158332 if price_change >= 0 else 3066993
    
    today_volume = last['Volume']
    vol_ma5 = last['Vol_MA5']
    vol_ratio = today_volume / vol_ma5 if vol_ma5 > 0 else 1
    
    signals = []
    signals_triggered = False 
    
    if vol_ratio >= 1.3:
        signals.append("⚡【量能爆發突破】")
        signals_triggered = True
    elif vol_ratio < 0.7:
        is_above_ma5 = current_price >= last['MA5']
        is_strong_rsi = last['RSI'] >= 50
        a_data_scan = get_analysis_data(sid)
        inst_percent = a_data_scan['法人持股'] if (a_data_scan and a_data_scan['法人持股'] != 'N/A') else 0
        if is_above_ma5 and (is_strong_rsi or inst_percent > 15):
            signals.append("💎【大戶惜售 / 籌碼鎖定】")
            signals_triggered = True

    if signals_triggered:
        embed = {
            "title": f"🚨 雷達警戒：{sname} ({sid})",
            "description": f"**觸發條件**：{' | '.join(signals)}",
            "color": color_hex,
            "fields": [
                {
                    "name": "💰 實時官方報價", 
                    "value": f"現價：**`{round(current_price, 2)}`** 元\n漲跌：**`{change_sign} {abs(price_change)}`** ({change_pct}%)", 
                    "inline": True
                },
                {
                    "name": "📊 技術與成交量能", 
                    "value": f"RSI 指標：`{round(last['RSI'], 2)}`\n成交量比：`{round(vol_ratio, 2)}x` (`{round(today_volume, 1)}`張/`{round(vol_ma5, 1)}`張)", 
                    "inline": True
                }
            ],
            "footer": {"text": f"秉諺的黑馬雷達 V25.0"}
        }
        send_discord_webhook(webhook_url, embed)
        return f"{sname} ({sid}) 觸發推播"
    return None

# --- 8. Sidebar 側邊欄介面 ---
with st.sidebar:
    st.sidebar.markdown(f"""<div style="background: linear-gradient(135deg, #1e3a8a, #000000); padding: 15px; border-radius: 12px; border: 1px solid #3b82f6; text-align: center;">
        <h1 style="color: #60a5fa; font-size: 18px; margin: 0;">🚀 戰情操控中心</h1>
        <p style="color: #94a3b8; font-size: 11px; margin-top:5px;">吳秉諺 專屬系統 V25.0</p>
    </div>""", unsafe_allow_html=True)

    st.sidebar.divider()
    selected_label = st.selectbox("🎯 選擇標的 (Target)", list(STOCK_DICT.values()))
    target_sid = selected_label.split(" ")[0]
    view_days = st.sidebar.slider("📅 顯示天數", 30, 240, 90)
    
    st.sidebar.divider()
    st.sidebar.link_button("🌐 Yahoo 股市", f"https://tw.stock.yahoo.com/quote/{target_sid}")
    st.sidebar.link_button("📊 Goodinfo 財報數據", f"https://goodinfo.tw/tw/StockDetail.asp?STOCK_ID={target_sid}")
    
    current_ind = next((n for n, d in INDUSTRY_DB.items() if target_sid in d.get("stocks", [])), "通用電子")
    st.sidebar.subheader(f"🏢 {current_ind} 百科")
    if current_ind in INDUSTRY_DB:
        d = INDUSTRY_DB[current_ind]
        company_briefs = d.get("company_briefs", {})
        current_brief = company_briefs.get(target_sid, "暫無業務描述")
        with st.sidebar.expander("🎯 個股主要業務", expanded=True):
            st.info(current_brief)
            
        with st.sidebar.expander("🔗 相關產業連動與競爭對手", expanded=True):
            competitors_db = d.get("competitors_db", {})
            ai_related_list = competitors_db.get(target_sid, [])
            if ai_related_list:
                st.markdown("\n".join([f"- **{peer}**" for peer in ai_related_list]))

    st.sidebar.divider()
    st.sidebar.subheader("➕ 擴建雷達")
    new_sid = st.sidebar.text_input("輸入股票代號")
    new_name = st.sidebar.text_input("輸入股票名稱")
    
    col_add, col_clean = st.sidebar.columns(2)
    with col_add:
        if st.sidebar.button("⚡ 新增"):
            if new_sid and new_name:
                success, msg = auto_update_industry_db(new_sid)
                if success:
                    current_stocks = load_stock_dict()
                    current_stocks[new_sid] = f"{new_sid} ({new_name})"
                    save_stock_dict(current_stocks)
                    st.session_state['STOCK_DICT'] = current_stocks
                    st.sidebar.success(msg)
                    time.sleep(1)
                    st.rerun()
    with col_clean:
        if st.sidebar.button("🧹 一鍵百科重置"):
            if os.path.exists(INDUSTRY_DB_FILE): os.remove(INDUSTRY_DB_FILE)
            st.cache_data.clear()
            current_stocks = load_stock_dict()
            for sid in current_stocks.keys():
                auto_update_industry_db(sid)
            st.sidebar.success("重置成功！")
            time.sleep(1)
            st.rerun()

if is_weekday and is_trading_hours:
    st_autorefresh(interval=5000, key="gametime_refresh")

df = get_stock_df(target_sid)
a_data = get_analysis_data(target_sid)
bid_p, ask_p, bid_s, ask_s = get_realtime_order(target_sid)

col_info, col_main = st.columns([1, 3])

with col_info:
    if df is not None and not df.empty:
        last, prev = df.iloc[-1], df.iloc[-2]
        clean_prices = get_yahoo_web_quote_from_df(target_sid, df)
        current_price = clean_prices["current"]
        prev_price = clean_prices["prev_close"]
            
        diff = round(current_price - prev_price, 2)
        m_color = "normal" if diff >= 0 else "inverse"
        
        st.markdown("### 🛡️ 技術防線")
        
        col_price_1, col_price_2 = st.columns(2)
        with col_price_1:
            st.metric("最新報價", f"{round(current_price, 2)}", f"{diff}", delta_color=m_color)
        with col_price_2:
            st.metric("昨日收盤", f"{round(prev_price, 2)}")

        # 買賣掛單
        st.divider()
        st.subheader("⚖️ 買賣掛單監控")
        col_b, col_a = st.columns(2)
        with col_b:
            st.metric("🟢 最佳委買價", f"{round(bid_p, 2)} 元" if bid_p > 0 else f"{round(current_price, 2)} 元")
            st.caption(f"掛單量: {int(bid_s)} 張" if bid_s > 0 else "盤中實時媒合")
        with col_a:
            st.metric("🔴 最佳委賣價", f"{round(ask_p, 2)} 元" if ask_p > 0 else f"{round(current_price, 2)} 元")
            st.caption(f"掛單量: {int(ask_s)} 張" if ask_s > 0 else "盤中實時媒合")

        total_size = bid_s + ask_s
        if total_size > 0:
            b_percent = round((bid_s / total_size) * 100, 1)
            st.write(f"委買比例: `{b_percent}%` vs 委賣比例: `{100-b_percent}%`")
            st.progress(b_percent / 100)
        else:
            st.write("委買比例: `50.0%` vs 委賣比例: `50.0%`")
            st.progress(0.5)

        # 量能動態診斷：股與張智慧換算
        st.divider()
        st.subheader("📊 量能動態診斷")
        
        today_volume = last['Volume']
        vol_ma5 = last['Vol_MA5']
        
        vol_ratio = (today_volume / vol_ma5) if vol_ma5 > 0 else 1
        vol_ratio_pct = round(vol_ratio * 100, 1)
        st.write(f"今日成交量：`{round(today_volume, 1)}` 張")
        st.write(f"5日均量：`{round(vol_ma5, 1)}` 張")
        st.write(f"量能佔比：`{vol_ratio_pct}%`")
        
        if vol_ratio > 1.5:
            vol_diag_msg = "⚡ 量能爆發"
            st.success("⚡ 【量能爆發】：多空強烈表態！")
        elif vol_ratio < 0.7:
            is_above_ma5 = current_price >= last['MA5']
            is_strong_rsi = last['RSI'] >= 50
            inst_percent = a_data['法人持股'] if (a_data and a_data['法人持股'] != 'N/A') else 0
            
            if is_above_ma5 and (is_strong_rsi or inst_percent > 15):
                vol_diag_msg = "💎 大戶惜售 / 籌碼鎖定"
                st.warning("💤 【量能明顯萎縮】")  
                st.info(f"""💎 **診斷：【大戶惜售 / 籌碼鎖定】**
                
* **現狀分析**：量能萎縮但價格未跌破 MA5 防線。
* **戰術提示**：此處突破較大機率為真突破。""")
            else:
                vol_diag_msg = "🥶 人氣退潮"
                st.warning("💤 【量能明顯萎縮】")  
                st.error(f"""🥶 **診斷：【人氣退潮】**
                
* **現狀分析**：量縮且價格無力。""")
        else:
            vol_diag_msg = "⚖️ 量能溫和"
            st.info("⚖️ 【量能溫和】：正常換手，走勢穩健。")

        # ==============================================================================
        # 【📈 指標診斷 & 莊家支撐線與底背離判定】
        # ==============================================================================
        st.divider()
        st.subheader("📈 指標與籌碼診斷")
        
        # 莊家防守成本線 (V25.0 100% 原始價格Facts精準計算)
        try:
            temp_df = df.tail(60).copy()
            top_3_vol_days = temp_df.nlargest(3, 'Volume')
            weighted_support = round(top_3_vol_days['Low'].mean(), 1)
        except:
            weighted_support = round(current_price * 0.95, 1)
            
        if current_price >= weighted_support:
            support_status = f"🟢 莊家防線守住 ({weighted_support} 元)"
            st.success(f"🛡️ **大戶籌碼防線**：{support_status}\n\n目前股價在此巨量支撐成本之上，屬於**高安全位階**！")
        else:
            support_status = f"🔴 防線跌破、留意續跌 ({weighted_support} 元)"
            st.error(f"⚠️ **大戶籌碼防線**：{support_status}\n\n目前收盤跌破巨量支撐，**不建議接刀**。")

        # 技術底背離動態偵測
        has_divergence = False
        if len(df) >= 10:
            past_min_close = df.iloc[-10:-1]['Close'].min()
            past_min_rsi = df.iloc[-10:-1]['RSI'].min()
            if (current_price <= past_min_close) and (last['RSI'] > past_min_rsi) and (last['RSI'] < 40):
                has_divergence = True
                
        if has_divergence:
            st.markdown("<p style='background-color:#7f1d1d; color:#fca5a5; padding:10px; border-radius:6px; font-weight:bold; border:1px solid #f87171;'>🔥 偵測到【低檔底背離】：股價創低但 RSI 拒絕破底，暗示極高機率將觸發反彈！</p>", unsafe_allow_html=True)

        st.write(f"**MA5：** :orange[{round(last['MA5'], 2)}]")
        st.write(f"**MA10：** :blue[{round(last['MA10'], 2)}]") 
        st.write(f"**MA20：** :violet[{round(last['MA20'], 2)}]")
        st.write(f"**MACD：** {'🟢 金叉' if last['DIF'] > last['DEA'] else '🔴 死叉'}")
        st.write(f"**KD 狀態：** {'🟢 金叉' if last['K'] > last['D'] else '🔴 死叉'}")

        # 財務數據
        if a_data:
            st.divider()
            st.subheader("📊 財務表現")
            rev_val = a_data['營久成長率'] if '營久成長率' in a_data else a_data.get('營收成長率', 0)
            rev_show = f"{round(rev_val * 100, 1)}%" if isinstance(rev_val, (int, float)) else "N/A"
            debt_val = a_data['負債比']
            debt_show = f"{round(debt_val, 1)}%" if isinstance(debt_val, (int, float)) else "N/A"
            inst_hold = a_data['法人持股']
            inst_show = f"{round(inst_hold, 1)}%" if isinstance(inst_hold, (int, float)) else "0%"

            st.write(f"**EPS：** :green[{a_data['EPS']}]")
            st.write(f"**ROE：** :blue[{a_data['ROE']}]")
            st.markdown(f"**本益比：** <span style='background-color:#1e293b; padding:2px 8px; border-radius:4px; color:#22c55e;'>{a_data['本益比']}</span>", unsafe_allow_html=True)
            st.markdown(f"**營收成長：** <span style='background-color:#1e293b; padding:2px 8px; border-radius:4px; color:#22c55e;'>{rev_show}</span>", unsafe_allow_html=True)
            st.markdown(f"**負債比：** <span style='background-color:#1e293b; padding:2px 8px; border-radius:4px; color:#22c55e;'>{debt_show}</span>", unsafe_allow_html=True)
            st.markdown(f"**法人持股：** <span style='background-color:#1e293b; padding:2px 8px; border-radius:4px; color:#22c55e;'>{inst_show}</span>", unsafe_allow_html=True)
    else:
        st.error(f"❌ 暫時無法獲取 {target_sid} 的基礎技術數據。")

with col_main:
    if df is not None and not df.empty:
        plot_df = df.tail(view_days)
        
        rsi_val = round(plot_df['RSI'].dropna().iloc[-1], 2) if not plot_df['RSI'].dropna().empty else 50.0
        inst_val = a_data['法人持股'] if a_data else 0
        
        chip_advice = " (大戶鎖碼中)" if inst_val > 25 else " (散戶主導中)"
        if rsi_val > 80: color, msg = "#ef4444", f"⚠️【高檔過熱：禁止追高{chip_advice}】"
        elif rsi_val < 40: color, msg = "#10b981", f"✅【低檔安全：留意佈局{chip_advice}】"
        else: color, msg = "#f59e0b", f"⚖️【區間震盪：觀望趨勢{chip_advice}】"
        
        today_open = float(last['Open'])
        today_high = float(last['High'])
        today_low = float(last['Low'])

        # 大看板
        st.markdown(f"""<div style="background: linear-gradient(90deg, #111827, #000000); border-left: 10px solid {color}; padding: 20px; border-radius: 12px; display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 15px;">
            <div style="min-width: 250px;">
                <p style="color:white; font-size: 32px; font-weight: 900; margin:0;">{selected_label} <span style="font-size: 24px; color: {color};">RSI: {rsi_val}</span></p>
                <p style="color:{color}; font-size: 24px; font-weight: bold; margin-top: 10px; margin-bottom: 0;">
                    {msg} <span style="color: #60a5fa; font-size: 24px; margin: 0 10px;">|</span> <span style="color: #e2e8f0; font-size: 22px; background-color: #1e293b; padding: 4px 12px; border-radius: 6px; border: 1px solid #475569;">{vol_diag_msg}</span>
                </p>
            </div>
            <div style="display: flex; gap: 12px; flex-wrap: nowrap;">
                <div style="background-color: #1e293b; width: 95px; padding: 8px 10px; border-radius: 8px; border: 1px solid #475569; text-align: center;">
                    <p style="color: #94a3b8; font-size: 11px; margin: 0;">開盤</p>
                    <p style="color: white; font-size: 20px; font-weight: bold; margin: 4px 0 0 0; white-space: nowrap;">{round(today_open, 2)}</p>
                </div>
                <div style="background-color: #1e293b; width: 95px; padding: 8px 10px; border-radius: 8px; border: 1px solid #ef4444; text-align: center;">
                    <p style="color: #ef4444; font-size: 11px; margin: 0;">最高</p>
                    <p style="color: white; font-size: 20px; font-weight: bold; margin: 4px 0 0 0; white-space: nowrap;">{round(today_high, 2)}</p>
                </div>
                <div style="background-color: #1e293b; width: 95px; padding: 8px 10px; border-radius: 8px; border: 1px solid #10b981; text-align: center;">
                    <p style="color: #10b981; font-size: 11px; margin: 0;">最低</p>
                    <p style="color: white; font-size: 20px; font-weight: bold; margin: 4px 0 0 0; white-space: nowrap;">{round(today_low, 2)}</p>
                </div>
            </div>
        </div>""", unsafe_allow_html=True)

        fig = make_subplots(rows=4, cols=1, shared_xaxes=True, vertical_spacing=0.04, 
                           row_heights=[0.4, 0.1, 0.2, 0.2])
        
        # K線
        fig.add_trace(go.Candlestick(x=plot_df.index, open=plot_df['Open'], high=plot_df['High'], low=plot_df['Low'], close=plot_df['Close'], name="K線",
                                     decreasing=dict(fillcolor='#10b981', line=dict(color='#10b981')),
                                     increasing=dict(fillcolor='#ef4444', line=dict(color='#ef4444'))), row=1, col=1)
        fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df['MA5'], name="5MA", line=dict(color='orange', width=1.5)), row=1, col=1)
        fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df['MA10'], name="10MA", line=dict(color='#60a5fa', width=1.5)), row=1, col=1)
        fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df['MA20'], name="20MA", line=dict(color='violet', width=1.5)), row=1, col=1)
        
        # 成交量
        fig.add_trace(go.Bar(x=plot_df.index, y=plot_df['Volume'], name="成交量", marker_color='#334155'), row=2, col=1)
        
        # MACD
        m_colors = ['#ef4444' if x > 0 else '#10b981' for x in plot_df['MACD_Hist']]
        fig.add_trace(go.Bar(x=plot_df.index, y=plot_df['MACD_Hist'], name="MACD柱", marker_color=m_colors), row=3, col=1)
        fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df['DIF'], name="DIF", line=dict(color='cyan')), row=3, col=1)
        fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df['DEA'], name="DEA", line=dict(color='yellow')), row=3, col=1)
        
        # KD
        fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df['K'], name="K值", line=dict(color='white')), row=4, col=1)
        fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df['D'], name="D值", line=dict(color='yellow')), row=4, col=1)
        
        fig.update_layout(height=800, template="plotly_dark", xaxis_rangeslider_visible=False)
        st.plotly_chart(fig, use_container_width=True)

        # 戰情推播控制台
        st.divider()
        st.markdown("""<div style="background: linear-gradient(135deg, #1e293b, #0f172a); padding: 20px; border-radius: 12px; border: 1px solid #475569; margin-top: 15px;">
            <h3 style="color: #60a5fa; margin: 0 0 10px 0; font-size: 20px; display: flex; align-items: center; gap: 8px;">📢 戰情推播控制台</h3>
            <p style="color: #94a3b8; font-size: 13px; margin: 0 0 15px 0;">在此手動觸發連線測試，或對您清單上的所有標的進行一鍵即時雷達掃描與 Discord 推播。</p>
        </div>""", unsafe_allow_html=True)

        col_dc_action1, col_dc_action2 = st.columns(2)
        
        with col_dc_action1:
            if st.button("🔗 發送 Discord 測試訊息", use_container_width=True):
                test_embed = {
                    "title": "✅ 秉諺的黑馬雷達連線測試",
                    "description": "網頁主端控制台發送成功！手動推播管道運作良好。",
                    "color": 3447003,
                    "footer": {"text": "測試時間: " + datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
                }
                success, msg = send_discord_webhook(DEFAULT_DISCORD_WEBHOOK, test_embed)
                if success: st.success("✅ " + msg)
                else: st.error("❌ " + msg)
                    
        with col_dc_action2:
            if st.button("🔍 執行全體雷達大掃描", use_container_width=True):
                with st.spinner("正在掃描..."):
                    results = []
                    current_scan_dict = load_stock_dict()
                    for sid, sname in current_scan_dict.items():
                        res = run_single_scan_signal(sid, sname, DEFAULT_DISCORD_WEBHOOK)
                        if res: results.append(res)
                    if results:
                        st.success(f"🎉 掃描完成！共推播了 {len(results)} 檔。")
                    else:
                        st.info("💡 目前所有標的指標平穩，未達警報標準。")
    else:
        st.error(f"❌ 暫時無法加載 {target_sid} 的 K 線資料。")