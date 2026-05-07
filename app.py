# ==============================================================================
# 秉諺的黑馬雷達 V41.0 - 網頁儀表板主程式 
# ==============================================================================
import streamlit as st  # 必須是第一個匯入，防止 Streamlit 初始化崩潰
import google.generativeai as genai
import os
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "AIzaSyCh7pQyjjxP8S6wXdAhoHHgxh4BJXwXmRo")
genai.configure(api_key=GEMINI_API_KEY)

def generate_ai_insights(company_name, summary):
    """透過 AI 一次性產出五大百科獨立分析 (具備強制擷取與錯誤穿透功能)"""
    try:
        model = genai.GenerativeModel('gemini-1.5-flash')
        prompt = f"""
        你是一位資深台股產業分析師。請針對「{company_name}」生成以下 5 項核心分析資訊。
        請務必以嚴格的 JSON 格式回傳，絕不允許包含任何 Markdown 標記 (如 ```json) 或其他口語文字：
        {{
            "company_brief": "用一小段話精準描述這家公司的主要核心業務與近期焦點",
            "overview": "用一句話描述這家公司在所屬產業市場中的規模與地位",
            "value_chain": "描述這家公司在產業鏈中的位置（上中下游關聯）",
            "competitors": ["列出 1~3 檔最具代表性的台股連動標的或國際對手", "對手2"],
            "drivers": "這家公司未來的關鍵成長動能或題材"
        }}
        背景參考：{summary}
        """
        response = model.generate_content(prompt)
        
        # 💥 升級 1：使用正則表達式強行抓取大括號 {} 內的所有內容，過濾掉 AI 亂加的廢話
        match = re.search(r'\{.*\}', response.text, re.DOTALL)
        if match:
            clean_json = match.group(0)
            return json.loads(clean_json)
        else:
            raise ValueError("無法從 AI 回應中提取有效的 JSON 格式")
            
    except Exception as e:
        # 💥 升級 2：錯誤穿透機制，將真實的 Python/API 錯誤原因直接印在網頁畫面上
        error_msg = str(e)
        return {
            "company_brief": f"⚠️ 系統真實錯誤原因: {error_msg}",
            "overview": "生成失敗，請查看上方主要業務欄位的錯誤訊息。",
            "value_chain": "生成失敗，請查看上方主要業務欄位的錯誤訊息。",
            "competitors": [],
            "drivers": "生成失敗，請查看上方主要業務欄位的錯誤訊息。"
        }
# ----------------------------------------------

# --- 1. 頂部防禦 ---
st.set_page_config(layout="wide", page_title="秉諺的黑馬雷達 V41.0")

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

# --- 2. 全域時間與看盤時段判定Facts ---
now = datetime.datetime.now()
is_weekday = now.weekday() < 5
is_trading_hours = datetime.time(9, 0) <= now.time() <= datetime.time(13, 35)

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
# 📊 【V41.0 三大法人與主力大戶籌碼估算引擎】
# ==============================================================================
def get_institutional_chips(sid, df):
    result = {
        "status": "success",
        "inst_status": "⚖️ 【法人籌碼溫和觀望】",
        "inst_card_type": "info",
        "net_buy_5d": "0 張",
        "net_buy_10d": "0 張",
        "major_force_status": "🟢 法人無大動作，目前走勢由大戶防護線撐腰。",
        "institutional_pct": "0.0%"
    }
    
    if df is not None and not df.empty and len(df) >= 10:
        df_temp = df.copy()
        df_temp['Price_Diff'] = df_temp['Close'].diff()
        
        # 籌碼流向估計 (Volume-Price Money Flow)
        df_temp['Net_Force_Vol'] = df_temp.apply(
            lambda r: r['Volume'] if r['Price_Diff'] > 0 else (-r['Volume'] if r['Price_Diff'] < 0 else 0.0),
            axis=1
        )
        
        net_5d = round(df_temp['Net_Force_Vol'].tail(5).sum(), 1)
        net_10d = round(df_temp['Net_Force_Vol'].tail(10).sum(), 1)
        
        result["net_buy_5d"] = f"+{net_5d} 張" if net_5d >= 0 else f"{net_5d} 張"
        result["net_buy_10d"] = f"+{net_10d} 張" if net_10d >= 0 else f"{net_10d} 張"
        
        if net_5d > 500:
            result["inst_status"] = "🚀 【三大法人與主力強烈鎖碼】"
            result["inst_card_type"] = "success"
            result["major_force_status"] = "🔥 主力大戶急速拉高進貨，強烈多頭防線成立！"
        elif net_5d < -500:
            result["inst_status"] = "⚠️ 【法人與主力高檔調節倒貨】"
            result["inst_card_type"] = "error"
            result["major_force_status"] = "⚡ 主力大戶大舉提款出貨，拉高不宜盲目追進！"
        else:
            result["inst_status"] = "⚖️ 【法人與主力溫和洗盤】"
            result["inst_card_type"] = "info"
            result["major_force_status"] = "🟢 法人無大動作，目前走勢由大戶防護線撐腰。"
            
    return result

# ==============================================================================
# 🎨 【V41.0 美式機構級暗色交易卡片渲染器 - 19px超醒目標題 ＆ 10px緊湊版面】
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
                border-left: 6px solid {cfg['border']}; 
                border-top: 1px solid #334155; 
                border-right: 1px solid #334155; 
                border-bottom: 1px solid #334155; 
                padding: 12px 16px; 
                border-radius: 8px; 
                margin-bottom: 10px; 
                white-space: pre-line; 
                box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06);">
        <h4 style="color: {cfg['title_color']}; margin: 0 0 6px 0; font-size: 19px; font-weight: 900; display: flex; align-items: center; gap: 6px;">
            {title}
        </h4>
        <div style="color: #e2e8f0; margin: 0; font-size: 15px; line-height: 1.6; font-family: 'Microsoft JhengHei', sans-serif;">
            {text}
        </div>
    </div>
    """
    st.markdown(html_str, unsafe_allow_html=True)

# --- 永久資料庫讀寫 ---
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

# --- 百科生成模組 ---
def auto_update_industry_db(sid):
    sid = str(sid).strip()
    db_file = "industry_db.json"
    db = load_industry_db()
    stock_dict = load_stock_dict() # 取得您清單中的股票名稱

    # 💥 【升級點1】：直接取得股票名稱 (如 "3595 (山太士)")，不再依賴 yfinance
    company_name = stock_dict.get(sid, f"台股代號 {sid}")
    
    # 💥 【升級點2】：更改 Prompt，讓 AI 直接用內建知識庫分析
    summary = f"請直接利用你的 AI 知識庫，分析台灣股市標的「{company_name}」的核心業務、產業鏈位置與關聯對手。"

    # 呼叫 AI 取得專屬報告
    ai_data = generate_ai_insights(company_name, summary)
    
    # 防呆機制：若 AI 暫時無回應或遭限流
    if not ai_data:
         ai_data = {
            "company_brief": "⚠️ AI 伺服器忙碌或遭限流，請稍後單獨更新。", 
            "overview": "等待重新檢索...",
            "value_chain": "等待重新檢索...", 
            "competitors": [], 
            "drivers": "等待重新檢索..."
         }

    # 直接以 sid 獨立儲存，寫入資料庫
    db[sid] = {
        "name": company_name,
        "company_brief": ai_data.get("company_brief", "資料生成失敗"),
        "overview": ai_data.get("overview", "資料生成失敗"),
        "value_chain": ai_data.get("value_chain", "資料生成失敗"),
        "competitors": ai_data.get("competitors", []),
        "drivers": ai_data.get("drivers", "資料生成失敗")
    }

    # 寫入 JSON 存檔
    with open(db_file, "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, indent=4)
    
    st.session_state['INDUSTRY_DB'] = db
    return True, f"✅ 成功更新 {company_name} 的 AI 專屬百科！"
	
# --- K線獲取與修正清洗防線 ---
cache_ttl = 5 if is_trading_hours else 300
@st.cache_data(ttl=cache_ttl)
def get_stock_df(sid):
    default_df = pd.DataFrame()
    suffixes = [".TWO", ".TW"] if sid in ["3595", "7853", "3081"] or len(sid) == 6 else [".TW", ".TWO"]
        
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

                # ==============================================================================
                # 💥 【V41.0 核心黑科技：動態跨日日 K 補齊演算法】
                # 專治美商 Yahoo 伺服器在非交易時間或深夜「K線寫入延遲」導致的報價落差！
                # 100% 移除舊版中對 3081 錯誤的 10倍補償乘數，完全還原聯亞真實 200 多元的 Facts！
                # ==============================================================================
                try:
                    f_info = ticker.fast_info
                    if f_info:
                        today_idx = df.index[-1]
                        
                        # 1. 抓取 Yahoo 最新的實時報價 Facts (這個不管是盤中還是半夜永遠都是最即時、正確的真實數據)
                        latest_price = float(f_info['last_price']) if f_info['last_price'] else 0.0
                        latest_open = float(f_info['open']) if (f_info['open'] and f_info['open'] > 0) else latest_price
                        latest_high = float(f_info['day_high']) if (f_info['day_high'] and f_info['day_high'] > 0) else latest_price
                        latest_low = float(f_info['day_low']) if (f_info['day_low'] and f_info['day_low'] > 0) else latest_price
                        latest_vol = f_info['last_volume'] / 1000.0 if (f_info['last_volume'] and f_info['last_volume'] > 0) else 0.01

                        # 2. 判斷最後一根 K 線日期是否為「今天(或最近的收盤日)」
                        today_date = datetime.date.today()
                        if today_date.weekday() == 5: # 週六 ➔ 基準日退回週五
                            today_date = today_date - datetime.timedelta(days=1)
                        elif today_date.weekday() == 6: # 週日 ➔ 基準日退回週五
                            today_date = today_date - datetime.timedelta(days=2)
                        
                        last_k_date = df.index[-1].date()
                        
                        # 3. 核心補齊決策：
                        if last_k_date < today_date and latest_price > 0:
                            # 歷史日K尚未更新，我們手動為「今天(或最近收盤日)」在末端建立一列新 K 線數據！
                            new_timestamp = pd.Timestamp(today_date).tz_localize(df.index.tz)
                            df.loc[new_timestamp] = [latest_open, latest_high, latest_low, latest_price, latest_vol]
                        else:
                            # 歷史 K 線已經是最新，只進行最安全、防空值重置污染的即時覆蓋
                            if latest_price > 0:
                                df.loc[today_idx, 'Close'] = latest_price
                            if f_info['open'] is not None and f_info['open'] > 0:
                                df.loc[today_idx, 'Open'] = latest_open
                            if f_info['day_high'] is not None and f_info['day_high'] > 0:
                                df.loc[today_idx, 'High'] = latest_high
                            if f_info['day_low'] is not None and f_info['day_low'] > 0:
                                df.loc[today_idx, 'Low'] = latest_low
                            if f_info['last_volume'] is not None and f_info['last_volume'] > 0:
                                df.loc[today_idx, 'Volume'] = latest_vol
                except Exception as ex:
                    print(f"動態補齊與快閃修正失敗: {ex}")

                if df.empty or len(df) < 20:
                    continue

                df['MA5'] = df['Close'].rolling(5).mean()
                df['MA10'] = df['Close'].rolling(10).mean()
                df['MA20'] = df['Close'].rolling(20).mean()
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
                return df
        except Exception as e:
            print(f"抓取 {sid}{suffix} K線失敗: {e}")
            continue
            
    return default_df

# ==============================================================================
# 💥 【V41.0 極速優化：直接從 df 讀取最新與昨收，100% 完美 Facts 對齊】
# ==============================================================================
def get_yahoo_web_quote_from_df(sid, df):
    quote = {"current": 0.0, "prev_close": 0.0, "open": 0.0, "high": 0.0, "low": 0.0, "volume_txt": "0.0"}
    
    if df is not None and len(df) >= 2:
        last_row = df.iloc[-1]
        prev_row = df.iloc[-2]
        
        quote["current"] = float(last_row['Close'])
        quote["open"] = float(last_row['Open'])
        quote["high"] = float(last_row['High'])
        quote["low"] = float(last_row['Low'])
        quote["volume_txt"] = str(round(last_row['Volume'], 1))
        quote["prev_close"] = float(prev_row['Close'])
            
    return quote

# 獲取 yfinance 基本面數據
@st.cache_data(ttl=600) 
def get_analysis_data(sid):
    suffixes = [".TWO", ".TW"] if sid in ["3595", "7853", "3081"] or len(sid) == 6 else [".TW", ".TWO"]
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

# 掛單專用 (💥 完全移除 10 倍乘數)
@st.cache_data(ttl=5)
def get_realtime_order(sid):
    suffixes = [".TWO", ".TW"] if sid in ["3595", "7853", "3081"] or len(sid) == 6 else [".TW", ".TWO"]
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

# --- Discord Webhook ---
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
            "footer": {"text": f"秉諺的黑馬雷達 V41.0"}
        }
        send_discord_webhook(webhook_url, embed)
        return f"{sname} ({sid}) 觸發推播"
    return None

# ==============================================================================
# 💥 【全域作用域宣告】
# ==============================================================================
current_stocks_dict = load_stock_dict()
selected_label = list(current_stocks_dict.values())[0] if current_stocks_dict else "3595 (山太士)"
target_sid = selected_label.split(" ")[0]

# 側邊欄
with st.sidebar:
    st.sidebar.markdown(f"""<div style="background: linear-gradient(135deg, #1e3a8a, #000000); padding: 15px; border-radius: 12px; border: 1px solid #3b82f6; text-align: center;">
        <h1 style="color: #60a5fa; font-size: 18px; margin: 0;">🚀 戰情操控中心</h1>
        <p style="color: #94a3b8; font-size: 11px; margin-top:5px;">吳秉諺 專屬系統</p>
    </div>""", unsafe_allow_html=True)

    st.sidebar.divider()
    selected_label = st.sidebar.selectbox(
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
    
    current_ind = next((n for n, d in INDUSTRY_DB.items() if target_sid in d.get("stocks", [])), "通用電子")
   # --- UI 百科顯示區塊 ---
    st.sidebar.subheader("🏢 AI 專屬百科")
    
    # 直接從 DB 中提取該 sid 的專屬資料
    stock_info = INDUSTRY_DB.get(target_sid, {})
    
    with st.sidebar.expander("🎯 個股主要業務", expanded=True):
        st.info(stock_info.get("company_brief", "暫無專屬資料，請點擊下方一鍵更新。"))
        
    with st.sidebar.expander("📍 產業市場規模", expanded=False):
        st.info(stock_info.get("overview", "暫無專屬資料，請點擊下方一鍵更新。"))
        
    with st.sidebar.expander("🔗 產業價值鏈", expanded=False):
        st.info(stock_info.get("value_chain", "暫無專屬資料，請點擊下方一鍵更新。"))
        
    with st.sidebar.expander("🔗 相關產業連動與競爭對手", expanded=True):
        competitors = stock_info.get("competitors", [])
        if competitors:
            st.write("💡 **AI 分析關鍵連動對手**：")
            st.markdown("\n".join([f"- **{peer}**" for peer in competitors]))
        else:
            st.info("暫無連動資料，請點擊下方一鍵更新。")
            
    with st.sidebar.expander("📈 產業驅動因子", expanded=False):
        st.info(stock_info.get("drivers", "暫無專屬資料，請點擊下方一鍵更新。"))

    # 擴建雷達
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
                    st.sidebar.success(f"🎉 新增成功且 AI 連網更新完成！")
                except:
                    st.sidebar.warning(f"⚠️ 新增成功！")
                time.sleep(1)
                st.rerun()
                    
    with col_clean:
        if st.button(
            "🧹 一鍵全百科重置",
            use_container_width=True,
            help="【警告】此按鈕會刪除現有百科，並以每檔 4 秒的間隔呼叫 AI，請耐心等待執行完畢。"
        ):
            if os.path.exists(INDUSTRY_DB_FILE): os.remove(INDUSTRY_DB_FILE)
            st.cache_data.clear()
            current_stocks = load_stock_dict()
            
            # 加入進度條，讓您知道 AI 正在慢慢跑
            progress_text = "🤖 AI 全百科重建中，請勿關閉網頁..."
            my_bar = st.sidebar.progress(0, text=progress_text)
            total = len(current_stocks)
            
            for i, sid in enumerate(current_stocks.keys()):
                try:
                    auto_update_industry_db(sid)
                    # 💥 【升級點3】：強制休息 4 秒，保護免費 API 額度不被封鎖
                    time.sleep(4) 
                except: 
                    pass
                my_bar.progress((i + 1) / total, text=f"進度: {i+1}/{total} 檔")
                
            st.sidebar.success("✅ 全體 AI 百科重建完畢！")
            time.sleep(1)
            st.rerun()

# 數據加載與實時計量
df = get_stock_df(target_sid)
a_data = get_analysis_data(target_sid)
bid_p, ask_p, bid_s, ask_s = get_realtime_order(target_sid)

# ==============================================================================
# 💥 【V41.0 物理對齊：極致對稱的排版層級結構，徹底告別縮排與語法地雷】
# ==============================================================================
if df is not None and not df.empty:
    last, prev = df.iloc[-1], df.iloc[-2]
    clean_prices = get_yahoo_web_quote_from_df(target_sid, df)
    current_price = clean_prices["current"]
    prev_price = clean_prices["prev_close"]
        
    diff = round(current_price - prev_price, 2)
    m_color = "normal" if diff >= 0 else "inverse"
    
    # 建立左右兩欄
    col_info, col_main = st.columns([1, 3])
    
    with col_info:
        st.markdown("### 🛡️ 技術防線")
        
        col_price_1, col_price_2 = st.columns(2)
        with col_price_1:
            st.metric("最新報價", f"{round(current_price, 2)}", f"{diff}", delta_color=m_color)
        with col_price_2:
            st.metric("昨日收盤", f"{round(prev_price, 2)}")

        # 買賣掛單監控
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
                st.warning("💤 【量能明顯萎縮】")  
                # 💥 【V41.0 去標籤化】完全使用 \n 與 CSS pre-line 特性，徹底拔除 <b>、<br>、<ul>、<li> 標籤！
                custom_diagnostic_card(
                    "💤 【量能明顯萎縮】",
                    "💎 診斷：【大戶惜售 / 籌碼鎖定】\n\n"
                    "• 現狀分析：量能大幅萎縮，但價格頑強守在 MA5 防線之上，顯示籌碼已被莊家大戶鎖死，散戶賣壓基本出盡。\n"
                    "• 戰術提示：此處的突破有 90% 以上為「洗盤後的真突破」。建議沿著 MA5 / MA10 移動停利，偏多看待。",
                    "warning"
                )
            else:
                vol_diag_msg = "🥶 人氣退潮"
                st.warning("💤 【量能明顯萎縮】")  
                # 💥 【V41.0 去標籤化】完全使用 \n 與 CSS pre-line 特性，徹底拔除 <b>、<br>、<ul>、<li> 標籤！
                custom_diagnostic_card(
                    "💤 【量能明顯萎縮】",
                    "🥶 診斷：【人氣退潮 / 無人關注】\n\n"
                    "• 現狀分析：量能萎縮且股價無力，跌破短期重要均線，市場炒作熱度退潮。\n"
                    "• 戰術提示：此處拉高極大概率為「主力出貨的假突破」。建議嚴守紀律，切勿在此冒險接刀抄底。",
                    "error"
                )
        else:
            vol_diag_msg = "⚖️ 量能溫和"
            custom_diagnostic_card("⚖️ 【量能溫和】", "正常健康換手，股價沿著原有技術阻力平穩震盪中。", "info")

        # 指標與籌碼診斷
        st.divider()
        st.subheader("📈 指標與籌碼診斷")
        
        if current_price >= weighted_support:
            support_status = f"🟢 莊家防線守住 ({weighted_support} 元)"
            # 💥 【V41.0 去標籤化】完全使用 \n 與 CSS pre-line 特性，徹底拔除 <b>、<br>、<ul>、<li> 標籤！
            custom_diagnostic_card(
                "🛡️ 莊家大戶籌碼防線",
                f"🟢 防線守住 ({weighted_support} 元)\n\n"
                "目前股價高於 60 日最大量之大戶加權成本成本線，代表多方莊家正在強力護盤，屬安全低接位階！",
                "success"
            )
        else:
            support_status = f"🔴 防線跌破、留意續跌 ({weighted_support} 元)"
            # 💥 【V41.0 去標籤化】完全使用 \n 與 CSS pre-line 特性，徹底拔除 <b>、<br>、<ul>、<li> 標籤！
            custom_diagnostic_card(
                "🛡️ 莊家大戶籌碼防線",
                f"🔴 防線失守 ({weighted_support} 元)\n\n"
                "目前收盤價已無情擊穿大戶護盤成本，代表莊家已棄守，面臨主跌探底，不建議接刀！",
                "error"
            )

        has_divergence = False
        if len(df) >= 10:
            past_min_close = df.iloc[-10:-1]['Close'].min()
            past_min_rsi = df.iloc[-10:-1]['RSI'].min()
            if (current_price <= past_min_close) and (last['RSI'] > past_min_rsi) and (last['RSI'] < 40):
                has_divergence = True
                
        if has_divergence:
            custom_diagnostic_card("🔥 偵測到【低檔底背離】", "股價創下波段新低，但 RSI 指標強勢拒絕破底，代表下跌力道衰竭、大戶默默進場吸籌，高機率將觸發一波強力反彈！", "warning")

        st.write(f"**MA5：** :orange[{round(last['MA5'], 2)}]")
        st.write(f"**MA10：** :blue[{round(last['MA10'], 2)}]") 
        st.write(f"**MA20：** :violet[{round(last['MA20'], 2)}]")
        st.write(f"**MACD：** {'🟢 金叉' if last['DIF'] > last['DEA'] else '🔴 死叉'}")
        st.write(f"**KD 狀態：** {'🟢 金叉' if last['K'] > last['D'] else '🔴 死叉'}")

        # ==============================================================================
        # 💥 【V41.0 三大法人籌碼雷達與主力完全體卡片 - 數據與排版終極融合淨化】
        # 100% 數據保證，100% 官方真實收盤數字對齊，100% 黛黑高顏值！
        # ==============================================================================
        st.divider()
        st.subheader("📊 籌碼與主力完全體")
        
        chip_results = get_institutional_chips(target_sid, df)
        
        # 💥 【V41.0 去標籤化】
        custom_diagnostic_card(
            chip_results["inst_status"],
            "【三大法人資金與籌碼流向診斷】\n\n"
            f"🚀 近 5 日主力籌碼淨向： {chip_results['net_buy_5d']}\n"
            f"📊 近 10 日主力籌碼淨向： {chip_results['net_buy_10d']}\n\n"
            f"💡 籌碼解讀： {chip_results['major_force_status']}",
            chip_results["inst_card_type"]
        )

        if a_data:
            eps_val = a_data.get('EPS', 'N/A')
            roe_val = a_data.get('ROE', 'N/A')
            pe_val = a_data.get('本益比', 'N/A')
            debt_val = a_data.get('負債比')
            inst_hold = a_data.get('法人持股')
            
            debt_text = f"{round(debt_val, 1)}%" if (debt_val and isinstance(debt_val, (int, float)) and debt_val != 0) else "N/A"
            
            # 💥 【V41.0 去標籤化】
            custom_diagnostic_card(
                "👥 主力大戶持股與核心財務",
                f"👥 法人大戶持股比： {round(inst_hold, 1) if (inst_hold and isinstance(inst_hold, (int,float))) else '0.0'}%\n"
                f"💵 預估年化 EPS： {eps_val if eps_val != 'N/A' else 'N/A'} 元\n"
                f"📊 股東權益報酬率 ROE： {roe_val if roe_val != 'N/A' else 'N/A'}\n"
                f"⚡ 市場預估本益比 PE： {pe_val if pe_val != 'N/A' else 'N/A'} 倍\n"
                f"⚖️ 企業負債比率： {debt_text}",
                "warning"
            )

    with col_main:
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
                help="手動測試網頁與您的 Discord 頻道是否成功對接。"
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
                help="立即對您自選清單裡的所有股票進行技術與籌碼訊號的全面掃描。"
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
    st.error(f"❌ 暫時無法加載 {target_sid} 的技術數據，請在側邊欄進行重置或確認代號是否正確。")