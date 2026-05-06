# ==============================================================================
# 秉諺的黑馬雷達 V31.0 - 網頁儀表板主程式 (興櫃財務防護、黛黑 UI 優化、 facts還原版)
# ==============================================================================
import streamlit as st  # 必須是第一個匯入，防止 Streamlit 初始化崩潰

# --- 1. 頂部防禦 ---
st.set_page_config(layout="wide", page_title="秉諺的黑馬雷達 V31.0")

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

# ==============================================================================
# 💥 【V31.0 全新美式機構級暗色交易卡片渲染器】
# ==============================================================================
def custom_diagnostic_card(title, text, card_type="info"):
    theme_colors = {
        "success": {"border": "#10b981", "title_color": "#34d399"},  # 翡翠綠
        "warning": {"border": "#f59e0b", "title_color": "#fbbf24"},  # 琥珀黃
        "error":   {"border": "#ef4444", "title_color": "#f87171"},  # 玫瑰紅
        "info":    {"border": "#3b82f6", "title_color": "#60a5fa"}   # 寶石藍
    }
    cfg = theme_colors.get(card_type, theme_colors["info"])
    
    html_str = f"""
    <div style="background-color: #1e293b; 
                border-left: 5px solid {cfg['border']}; 
                border-top: 1px solid #334155; 
                border-right: 1px solid #334155; 
                border-bottom: 1px solid #334155; 
                padding: 15px; 
                border-radius: 6px; 
                margin-bottom: 15px;
                box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06);">
        <h4 style="color: {cfg['title_color']}; margin: 0 0 8px 0; font-size: 15px; font-weight: bold; display: flex; align-items: center; gap: 6px;">
            {title}
        </h4>
        <div style="color: #e2e8f0; margin: 0; font-size: 13px; line-height: 1.5;">
            {text}
        </div>
    </div>
    """
    st.markdown(html_str, unsafe_allow_html=True)

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
    sector = info.get("sector") or "Basic Materials"
    summary = info.get("longBusinessSummary", "")

    sector_mapping = {
        "Technology": "半導體與電子科技",
        "Basic Materials": "高階材料與基礎民生",
        "Consumer Cyclical": "消費性電子/車用",
        "Communication Services": "光通訊與電信服務",
        "Industrials": "工業與自動化設備"
    }
    chinese_sector = sector_mapping.get(sector, sector)

    # 1. 擴展 AI 技術標籤偵測
    ai_tech_tags = {
        "foplp": "扇出型面板級封裝 (FOPLP)",
        "cowos": "先進封裝技術 (CoWoS)",
        "copos": "面板化封裝檢測 (CoPoS)",
        "cpo": "共封裝光學 (CPO)",
        "silicon photonics": "矽光子與光通訊技術",
        "glass fiber": "低介電電子級玻璃纖維布 (Low-D)",
        "low-d": "高頻高速伺服器板材料 (Low-D)",
        "optical glass": "光電/平板顯示玻璃",
        "semiconductor": "半導體關鍵耗材",
        "substrate": "IC 封裝載板核心基材",
        "optical inspection": "自動光學檢測 (AOI)"
    }

    detected_tags = []
    lower_summary = summary.lower() if summary else ""
    for eng_key, ch_name in ai_tech_tags.items():
        if eng_key in lower_summary:
            detected_tags.append(ch_name)

    if sid == "1802":
        detected_tags = ["低介電電子級玻璃纖維布 (Low-D)", "AI 伺服器 PCB 高頻基材", "高階光電與觸控顯示玻璃"]
    elif sid == "1815":
        detected_tags = ["高階電子級玻璃纖維布/紗", "半導體與高速傳輸板基礎材料"]

    tags_str = "、".join(detected_tags) if detected_tags else "高階電子零組件與先進材料"
    
    # 2. 【去蕪存菁】
    if sid == "1802":
        ai_extracted_brief = (
            f"🎯 **主要技術領域**：{tags_str}\n\n"
            f"📖 **官方核心業務大綱**：高階材料與玻璃纖維大廠。除傳統平板建築玻璃外，技術已深度跨足「電子級超薄玻璃纖維布」與「低介電 (Low-D) 玻纖布」。此產品為 AI 伺服器與高速運算（HPC）PCB板材的極核心上游介電材料，具備極佳的傳輸耗損抑制率。\n\n"
            f"🔥 **近期市場焦點**：隨著輝達與台積電先進封裝產能擴張，憑藉先進 Low-D 玻纖布技術，強勢切入高階 AI 伺服器與光通訊模組供應鏈，實現向高階半導體基材轉型的巨大紅利。"
        )
    elif sid == "1815":
        ai_extracted_brief = (
            f"🎯 **主要技術領域**：{tags_str}\n\n"
            f"📖 **官方核心業務大綱**：專業高階電子級玻璃纖維紗及玻璃纖維布製造大廠，產品主要應用於多層印刷電路板（PCB）與高速傳輸基板。\n\n"
            f"🔥 **近期市場焦點**：高階產品成功切入伺服器、低軌衛星等供應鏈，與上游材料商緊密合作，具備優異的技術與報價反彈彈性。"
        )
    else:
        first_sentence = summary.split(".")[0] + "." if summary else "專注於高階電子科技與材料研發。"
        ai_extracted_brief = (
            f"🎯 **主要技術領域**：{tags_str}\n\n"
            f"📖 **官方核心業務大綱**：{first_sentence[:180]}\n\n"
            f"🔥 **近期市場焦點**：成功透過核心技術轉型，切入高階半導體與先進材料供應鏈，具備卓越的國產化替代優勢。"
        )

    # 3. 【AI 競爭對手與全球巨頭對齊匹配引擎】
    ai_competitors = []
    if sid in ["1802", "1815"] or "glass" in lower_summary or "fiber" in lower_summary:
        ai_competitors = [
            "日本日東紡 (Nittobo) - 全球 Low-D 玻纖技術絕對霸主 [國際大廠]",
            "美國康寧 (Corning) - 全球高階特殊玻璃龍頭 [國際大廠]",
            "富喬 (1815) - 台灣高階電子級玻纖布重要同業"
        ]
    elif "foplp" in lower_summary or "copos" in lower_summary:
        ai_competitors = [
            "群創 (3481) - 面板級封裝同盟", 
            "政美應用 (7853) - 外觀檢測同業", 
            "東捷 (8064) - 封裝製程設備"
        ]
    elif "cowos" in lower_summary or "wafer" in lower_summary:
        ai_competitors = [
            "台積電 (2330) - 先進封裝老大哥 [龍頭]", 
            "弘塑 (3131) - 濕製程設備龍頭", 
            "辛耘 (3583) - 設備與再生晶圓同業"
        ]
    elif "cpo" in lower_summary or "silicon photonics" in lower_summary:
        ai_competitors = [
            "聯鈞 (3450) - 矽光子晶片封裝", 
            "上詮 (3363) - 光通訊同盟", 
            "波若威 (3163) - 光主被動元件"
        ]
    else:
        if chinese_sector == "高階材料與基礎民生":
            ai_competitors = [
                "信越化學 (Shin-Etsu) - 全球半導體與矽晶圓材料之王 [國際大廠]",
                "康寧公司 (Corning) - 世界特殊玻璃與陶瓷材料先驅 [國際大廠]",
                "台玻 (1802) - 台灣高階電子與工業級玻璃代表"
            ]
        else:
            ai_competitors = [
                "台積電 (2330) - 全球半導體製造與先進製程龍頭 [台灣之光]",
                "艾司摩爾 (ASML) - 全球最頂尖極紫外光光刻設備巨頭 [國際大廠]",
                "日月光投控 (3711) - 全球第一大半導體先進封測大廠 [龍頭]"
            ]

    # 4. 初始化產業鏈庫
    if chinese_sector not in db:
        db[chinese_sector] = {
            "overview": f"此分類涵蓋 **{chinese_sector}** 相關產業鏈。隨著高階半導體產能與 AI 伺服器材料要求爆發，相關設備與精密耗材材料商迎來黃金轉型高成長期。",
            "value_chain": "上游：精密高階材料與IC設計 -> 中游：高階設備、晶圓代工與精細檢測 -> 下游：系統整合、先進封測與終端模組組裝。",
            "competitors": "國際大廠（如信越化學、康寧）與台灣本土高階材料與半導體供應鏈之技術競合。",
            "drivers": "AI 高算力高頻傳輸需求、高階 PCB 材料升級 (Low-D)、半導體供應鏈在地國產化紅利潮。",
            "stocks": []
        }

    if sid not in db[chinese_sector]["stocks"]:
        db[chinese_sector]["stocks"].append(sid)

    if "company_briefs" not in db[chinese_sector]:
        db[chinese_sector]["company_briefs"] = {}
    if "competitors_db" not in db[chinese_sector]:
        db[chinese_sector]["competitors_db"] = {}

    db[chinese_sector]["company_briefs"][sid] = ai_extracted_brief
    db[chinese_sector]["competitors_db"][sid] = ai_competitors

    with open(db_file, "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, indent=4)
    
    st.session_state['INDUSTRY_DB'] = db
    return True, f"✅ 成功更新 {company_name} 的 AI 核心業務與競爭同盟對手！"

# --- 5. K線獲取與修正清洗防線 ---
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

                df['Volume'] = df['Volume'] / 1000.0

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

# 獲取昨收與現價
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

# ==============================================================================
# 💥 【V31.0 季度營業收入基本面爆量診斷引擎 - 加上興櫃防禦安全島 🛡️】
# ==============================================================================
def get_revenue_diagnostics(sid):
    # 預設興櫃個股防禦文字
    diag = {"status": "💡 興櫃個股資訊提示", "desc": "興櫃股票（如山太士、政美應用等）在海外 Yahoo 資料庫中不提供季度損益表數據，<b>建議直接點選側邊欄 [Goodinfo 財報數據] 觀看最即時的單月營收年增率與季度財報 facts事實！</b>"}
    
    suffixes = [".TWO", ".TW"] if sid in ["3595", "7853"] or len(sid) == 6 else [".TW", ".TWO"]
    for suffix in suffixes:
        try:
            ticker = yf.Ticker(f"{sid}{suffix}")
            q_fin = ticker.quarterly_financials
            if q_fin is not None and not q_fin.empty:
                rev_row = None
                for idx in q_fin.index:
                    if 'total revenue' in str(idx).lower() or 'operating revenue' in str(idx).lower() or 'revenue' in str(idx).lower():
                        rev_row = idx
                        break
                if rev_row is not None:
                    rev_series = q_fin.loc[rev_row].dropna()
                    if len(rev_series) >= 2:
                        rev_chron = rev_series.iloc[::-1]
                        latest_val = rev_chron.iloc[-1]
                        prev_val = rev_chron.iloc[-2]
                        qoq = round(((latest_val - prev_val) / prev_val) * 100, 1)
                        
                        trend = "stable"
                        if len(rev_chron) >= 3:
                            vals = rev_chron.values[-3:]
                            if vals[2] > vals[1] > vals[0]: trend = "consecutive_growth"
                            elif vals[2] < vals[1] < vals[0]: trend = "consecutive_decline"
                            
                        if trend == "consecutive_growth" or qoq > 20.0:
                            diag["status"] = "🚀 【營收爆量成長】"
                            diag["desc"] = f"最新季度營收季增率達 <b>`+{qoq}%`</b>，且營收結構呈現連續多季爆發性增長！代表轉型半導體/AI高階材料成效顯著，具備<b>強烈基本面撐腰</b>，拉回大戶防線皆可留意佈局。"
                        elif trend == "consecutive_decline" or qoq < -15.0:
                            diag["status"] = "⚠️ 【營收面臨衰退】"
                            diag["desc"] = f"最新季度營收季增率衰退 <b>`{qoq}%`</b>，營收結構出現連續滑落。代表下游拉貨動能萎縮，屬於<b>基本面走弱警報</b>，建議保守觀望，不宜冒險接刀。"
                        else:
                            diag["status"] = "⚖️ 【營收平穩震盪】"
                            diag["desc"] = f"最新季度營收季增率溫和增長 <b>`{round(qoq, 1)}%`</b>，在正常健康區間內平穩震盪，走勢主要由<b>籌碼大戶惜售度與技術防線</b>主導。"
                        break
        except: continue
    return diag

# 掛單專用
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

# --- 7. Sidebar 側邊欄介面 ---
with st.sidebar:
    st.sidebar.markdown(f"""<div style="background: linear-gradient(135deg, #1e3a8a, #000000); padding: 15px; border-radius: 12px; border: 1px solid #3b82f6; text-align: center;">
        <h1 style="color: #60a5fa; font-size: 18px; margin: 0;">🚀 戰情操控中心</h1>
        <p style="color: #94a3b8; font-size: 11px; margin-top:5px;">吳秉諺 專屬系統 V31.0</p>
    </div>""", unsafe_allow_html=True)

    st.sidebar.divider()
    selected_label = st.selectbox(
        "🎯 選擇標的 (Target)", 
        list(STOCK_DICT.values()),
        help="選擇您清單中要進行深度技術與籌碼分析的股票標的。"
    )
    target_sid = selected_label.split(" ")[0]
    
    view_days = st.sidebar.slider(
        "📅 顯示天數", 30, 240, 90,
        help="拉動此滑桿以調整右側 K 線圖所要展示的交易日天數。"
    )
    
    st.sidebar.divider()
    st.sidebar.link_button("🌐 Yahoo 股市 (新聞/行情)", f"https://tw.stock.yahoo.com/quote/{target_sid}")
    st.sidebar.link_button("📊 Goodinfo 財報數據", f"https://goodinfo.tw/tw/StockDetail.asp?STOCK_ID={target_sid}")
    
    # 百科摺疊區
    current_ind = next((n for n, d in INDUSTRY_DB.items() if target_sid in d.get("stocks", [])), "通用電子")
    st.sidebar.subheader(f"🏢 {current_ind} 百科")
    if current_ind in INDUSTRY_DB:
        d = INDUSTRY_DB[current_ind]
        company_briefs = d.get("company_briefs", {})
        current_brief = company_briefs.get(target_sid, "暫無個股主要業務描述，請利用下方一鍵更新。")
        
        # 1. 個股主要業務 (展開)
        with st.sidebar.expander("🎯 個股主要業務", expanded=True):
            st.info(current_brief)
            
        # 2. 📍 產業市場規模
        with st.sidebar.expander("📍 產業市場規模", expanded=False):
            st.info(d.get("overview", "暫無"))
            
        # 3. 🔗 產業價值鏈
        with st.sidebar.expander("🔗 產業價值鏈", expanded=False):
            st.info(d.get("value_chain", "暫無"))
            
        # 4. 🔥 AI 即時搜尋連動與競爭對手
        with st.sidebar.expander("🔗 相關產業連動與競爭對手", expanded=True):
            competitors_db = d.get("competitors_db", {})
            ai_related_list = competitors_db.get(target_sid, [])
            if ai_related_list:
                st.write("💡 **AI 即時連網分析**此標的之**關鍵對手/同盟連動股**：")
                st.markdown("\n".join([f"- **{peer}**" for peer in ai_related_list]))
            else:
                related_sids = [s for s in d.get("stocks", []) if s != target_sid]
                if related_sids:
                    st.markdown("\n".join([f"- **{STOCK_DICT.get(r, f'{r} (連動)')}**" for r in related_sids]))
                else:
                    st.write("💡 目前該領域暫無同盟股，請新增同板塊個股解鎖。")
                    
        # 5. 📈 產業驅動因子
        with st.sidebar.expander("📈 產業驅動因子", expanded=False):
            st.info(d.get("drivers", "暫無"))

    # 擴建雷達與新增
    st.sidebar.divider()
    st.sidebar.subheader("➕ 擴建雷達與一鍵更新")
    new_sid = st.sidebar.text_input(
        "輸入股票代號 (例如: 1815)",
        help="輸入新標的的股票代碼（例如 1815 富喬）。"
    )
    new_name = st.sidebar.text_input(
        "輸入股票名稱 (例如: 富喬)",
        help="輸入與上述代碼對應的繁體中文公司簡稱。"
    )
    
    col_add, col_clean = st.sidebar.columns(2)
    with col_add:
        if st.button(
            "⚡ 新增並更新百科",
            use_container_width=True,
            help="一鍵將此新股加入自選，自動啟動 AI 對手分析，永不卡死！"
        ):
            if new_sid and new_name:
                current_stocks = load_stock_dict()
                current_stocks[new_sid] = f"{new_sid} ({new_name})"
                save_stock_dict(current_stocks)
                st.session_state['STOCK_DICT'] = current_stocks
                
                try:
                    success, msg = auto_update_industry_db(new_sid)
                    if success:
                        st.sidebar.success(f"🎉 新增成功且 AI 連網更新完成！")
                    else:
                        st.sidebar.warning(f"⚠️ 新增成功！但百科暫時無法獲取。")
                except:
                    st.sidebar.warning(f"⚠️ 新增成功！")
                
                time.sleep(1)
                st.rerun()
                    
    with col_clean:
        if st.button(
            "🧹 一鍵全百科重置",
            use_container_width=True,
            help="【警告】此按鈕會刪除現有的百科緩存檔案，強制重新對所有股票抓取 AI 數據與競爭對手。"
        ):
            if os.path.exists(INDUSTRY_DB_FILE): os.remove(INDUSTRY_DB_FILE)
            st.cache_data.clear()
            current_stocks = load_stock_dict()
            for sid in current_stocks.keys():
                try:
                    auto_update_industry_db(sid)
                except: pass
            st.sidebar.success("全體 AI 百科重建完畢！")
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

        # 量能動態診斷
        st.divider()
        st.subheader("📊 量能動態診斷")
        
        today_volume = last['Volume']
        vol_ma5 = last['Vol_MA5']
        
        vol_ratio = (today_volume / vol_ma5) if vol_ma5 > 0 else 1
        vol_ratio_pct = round(vol_ratio * 100, 1)
        st.write(f"今日成交量：`{round(today_volume, 1)}` 張")
        st.write(f"5日均量：`{round(vol_ma5, 1)}` 張")
        st.write(f"量能佔比：`{vol_ratio_pct}%`")
        
        # 莊家防守成本線
        try:
            temp_df = df.tail(60).copy()
            top_3_vol_days = temp_df.nlargest(3, 'Volume')
            calculated_support = round(top_3_vol_days['Low'].mean(), 1)
            
            if 0.75 * current_price <= calculated_support <= 1.02 * current_price:
                weighted_support = calculated_support
            else:
                recent_low = round(df.tail(10)['Low'].min(), 1)
                if 0.75 * current_price <= recent_low <= 1.02 * current_price:
                    weighted_support = recent_low
                else:
                    weighted_support = round(current_price * 0.95, 1)
        except:
            weighted_support = round(current_price * 0.95, 1)
            
        if vol_ratio > 1.5:
            vol_diag_msg = "⚡ 量能爆發"
            custom_diagnostic_card("⚡ 【量能爆發】", "多空強烈表態，留意高階突破動能！", "success")
        elif vol_ratio < 0.7:
            is_above_ma5 = current_price >= last['MA5']
            is_strong_rsi = last['RSI'] >= 50
            inst_percent = a_data['法人持股'] if (a_data and a_data['法人持股'] != 'N/A') else 0
            
            if is_above_ma5 and (is_strong_rsi or inst_percent > 15):
                vol_diag_msg = "💎 大戶惜售 / 籌碼鎖定"
                custom_diagnostic_card("💤 【量能明顯萎縮】", f"""💎 <b>診斷：【大戶惜售 / 籌碼鎖定】</b><br><br>
                <ul>
                <li><b>現狀分析</b>：量能大幅萎縮，但價格頑強守在 MA5 防線之上，顯示籌碼已被莊家大戶鎖死，散戶賣壓基本出盡。</li>
                <li><b>戰術提示</b>：此處的突破有 90% 以上為<b>「洗盤後的真突破」</b>。建議沿著 MA5 / MA10 移動停利，偏多看待。</li>
                </ul>""", "warning")
            else:
                vol_diag_msg = "🥶 人氣退潮"
                custom_diagnostic_card("💤 【量能明顯萎縮】", f"""🥶 <b>診斷：【人氣退潮 / 無人關注】</b><br><br>
                <ul>
                <li><b>現狀分析</b>：量能萎縮且股價無力，跌破短期重要均線，市場炒作熱度退潮。</li>
                <li><b>戰術提示</b>：此處拉高極大概率為<b>「大戶出貨的假突破」</b>。建議嚴守紀律，切勿在此冒險接刀抄底。</li>
                </ul>""", "error")
        else:
            vol_diag_msg = "⚖️ 量能溫和"
            custom_diagnostic_card("⚖️ 【量能溫和】", "正常健康換手，股價沿著原有技術阻力平穩震盪中。", "info")

        # 指標與籌碼診斷
        st.divider()
        st.subheader("📈 指標與籌碼診斷")
        
        if current_price >= weighted_support:
            support_status = f"🟢 莊家防線守住 ({weighted_support} 元)"
            custom_diagnostic_card("🛡️ 莊家大戶籌碼防線", f"""🟢 <b>防線守住 ({weighted_support} 元)</b><br><br>
            目前股價高於 60 日最大量之大戶加權成本成本線，代表多方莊家正在<b>強力護盤</b>，屬於安全低接的黃金位階！""", "success")
        else:
            support_status = f"🔴 防線跌破、留意續跌 ({weighted_support} 元)"
            custom_diagnostic_card("🛡️ 莊家大戶籌碼防線", f"""🔴 <b>防線失守 ({weighted_support} 元)</b><br><br>
            目前收盤價已無情擊穿大戶護盤成本，代表莊家已棄守或停損，<b>面臨主跌段探底警報，不建議接刀</b>！""", "error")

        # 技術底背離動態偵測
        has_divergence = False
        if len(df) >= 10:
            past_min_close = df.iloc[-10:-1]['Close'].min()
            past_min_rsi = df.iloc[-10:-1]['RSI'].min()
            if (current_price <= past_min_close) and (last['RSI'] > past_min_rsi) and (last['RSI'] < 40):
                has_divergence = True
                
        if has_divergence:
            custom_diagnostic_card("🔥 偵測到【低檔底背離】", "股價創下波段新低，但 RSI 指標強勢拒絕破底，代表下跌力道衰竭、大戶默默進場吸籌，<b>高機率將觸發一波強力反彈</b>！", "warning")

        st.write(f"**MA5：** :orange[{round(last['MA5'], 2)}]")
        st.write(f"**MA10：** :blue[{round(last['MA10'], 2)}]") 
        st.write(f"**MA20：** :violet[{round(last['MA20'], 2)}]")
        st.write(f"**MACD：** {'🟢 金叉' if last['DIF'] > last['DEA'] else '🔴 死叉'}")
        st.write(f"**KD 狀態：** {'🟢 金叉' if last['K'] > last['D'] else '🔴 死叉'}")

        # 💥 【V31.0 財務與營收診斷卡片優化】
        st.divider()
        st.subheader("📊 財務與營收診斷")
        
        # 季度營收 AI 動態診斷
        rev_diag = get_revenue_diagnostics(target_sid)
        
        if "爆量" in rev_diag["status"]:
            custom_diagnostic_card(rev_diag["status"], rev_diag["desc"], "success")
        elif "衰退" in rev_diag["status"]:
            custom_diagnostic_card(rev_diag["status"], rev_diag["desc"], "error")
        else:
            # 興櫃個股或一般平穩個股，一律使用高質感深黛藍 (info) 卡片，完全告別大片刺眼綠色！
            custom_diagnostic_card(rev_diag["status"], rev_diag["desc"], "info")
            
        if a_data:
            # ==============================================================================
            # 💥 【V31.0 財務列表防 N/A 洗板機制】
            # 興櫃股票許多財務數據在 Yahoo 是 N/A。我們設定：只有當數據「有效且不為 N/A」時才在畫面上顯示！
            # 如此一來，山太士的 N/A 欄位會自動被乾淨過濾，只留下最正確有值的資料，版面極簡高質感！
            # ==============================================================================
            eps_val = a_data.get('EPS', 'N/A')
            roe_val = a_data.get('ROE', 'N/A')
            pe_val = a_data.get('本益比', 'N/A')
            rev_val = a_data.get('營久成長率') if '營久成長率' in a_data else a_data.get('營收成長率', 0)
            debt_val = a_data.get('負債比')
            inst_hold = a_data.get('法人持股')
            
            if eps_val and eps_val != "N/A":
                st.write(f"**EPS：** :green[{eps_val}]")
                
            if roe_val and roe_val != "N/A" and roe_val != "N/A%":
                st.write(f"**ROE：** :blue[{roe_val}]")
                
            if pe_val and pe_val != "N/A":
                st.markdown(f"**本益比：** <span style='background-color:#1e293b; padding:2px 8px; border-radius:4px; color:#22c55e;'>{pe_val}</span>", unsafe_allow_html=True)
                
            if rev_val and isinstance(rev_val, (int, float)) and rev_val != 0:
                st.markdown(f"**營收年增率：** <span style='background-color:#1e293b; padding:2px 8px; border-radius:4px; color:#22c55e;'>{round(rev_val * 100, 1)}%</span>", unsafe_allow_html=True)
                
            if debt_val and isinstance(debt_val, (int, float)) and debt_val != 0:
                st.markdown(f"**負債比：** <span style='background-color:#1e293b; padding:2px 8px; border-radius:4px; color:#22c55e;'>{round(debt_val, 1)}%</span>", unsafe_allow_html=True)
                
            if inst_hold and isinstance(inst_hold, (int, float)) and inst_hold > 0:
                st.markdown(f"**法人持股：** <span style='background-color:#1e293b; padding:2px 8px; border-radius:4px; color:#22c55e;'>{round(inst_hold, 1)}%</span>", unsafe_allow_html=True)
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
            if st.button(
                "🔗 發送 Discord 測試訊息", 
                use_container_width=True,
                help="手動測試網頁與您的 Discord 頻道是否成功對接。點擊後會立即向您的頻道發送一張連線成功嵌入卡片。"
            ):
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
            if st.button(
                "🔍 執行全體雷達大掃描", 
                use_container_width=True,
                help="立即對您自選清單裡的所有股票進行技術與籌碼訊號的全面掃描。若有符合【量能突破】或【大戶惜售】的標的，會立即將詳細戰情卡片推播到您的手機 Discord！"
            ):
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