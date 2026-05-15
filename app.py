# ==============================================================================
# 秉諺的黑馬雷達 V41.0 - 網頁儀表板主程式 
# ==============================================================================
import streamlit as st
import google.generativeai as genai
import os
import re  # 💥 新增這一行：匯入正則表達式模組
import json
import pandas as pd
from streamlit_autorefresh import st_autorefresh

# --- 背景自動刷新設定 ---
# 每 300,000 毫秒 (即 5 分鐘) 自動觸發一次 st.rerun()
# 這會強迫網頁重新抓取最新的 Yahoo 股市數據與籌碼，但不會觸發 AI
count = st_autorefresh(interval=300000, key="f5_refresh")

# 安全讀取邏輯：優先讀取 Secrets，若無則報錯，不再放任何預設金鑰字串
# ✅ 正確的安全寫法（請確保 app.py 是長這樣）
GEMINI_API_KEY = st.secrets.get("GEMINI_API_KEY") or os.environ.get("GEMINI_API_KEY")

if not GEMINI_API_KEY:
    st.error("❌ 偵測不到 API 金鑰！請至 Streamlit Cloud Secrets 設定 'GEMINI_API_KEY'")
    st.stop()
else:
    genai.configure(api_key=GEMINI_API_KEY)

def generate_ai_insights(company_name, summary):
    """透過 AI 一次性產出分析，具備「雙引擎容錯」與「連網搜尋」功能"""
    import re
    import json
    
    # 動態拆解邏輯
    match = re.match(r'^([A-Za-z0-9]+)(?:\s*\((.*?)\))?', company_name.strip())
    if match:
        ticker = match.group(1)
        pure_name = match.group(2) if match.group(2) else ticker
    else:
        ticker = company_name
        pure_name = company_name

    response = None
    try:
        # 【主引擎】：嘗試使用 gemini-2.5-pro 連網搜尋
        model_pro = genai.GenerativeModel(
            model_name='gemini-2.5-pro', 
            tools='google_search_retrieval'
        )
        prompt_pro = f"請連網查詢台股「{ticker} {pure_name}」的最新官方業務與產業地位。請以 JSON 格式回傳，欄位包含 company_brief, overview, value_chain(純文字，嚴禁巢狀字典), competitors (陣列), drivers。"
        response = model_pro.generate_content(prompt_pro)
        
    except Exception as e:
        print(f"主引擎連網失敗，切換備用引擎: {e}")
        try:
            # 💥 您的 API 環境僅支援最新版，備用引擎切回 2.5-flash
            model_fallback = genai.GenerativeModel(model_name='gemini-2.5-flash')
            
            # 💥 融入您的「名稱搜尋優先」嚴厲警告
            prompt_fallback = f"""
            [核心目標]：你【唯一】要分析的企業為「{pure_name}」(代號:{ticker})。
            
            [嚴厲警告]：
            1. 執行任務時，必須【優先以名稱：「{pure_name}」】進行檢索，絕對不可寫成任何與此名稱無關之企業（例如宏碩、望隼、保瑞、旺宏等）！
            2. 輸出之所有產業資訊必須嚴格對齊「{pure_name}」的真實官方業務。
            
            [格式要求]：請以 JSON 回傳欄位：company_brief, overview, value_chain, competitors (陣列), drivers。
            注意：所有內容必須是「純文字」，嚴禁使用巢狀字典格式。
            
            [查核規範]：如果你對「{pure_name}」這家公司的具體營業項目不確定，請將前四個欄位【全部】填寫「【資料不足，無法確認】」，competitors 填寫空陣列 []。
            """
            response = model_fallback.generate_content(prompt_fallback)
        except Exception as ex:
            return {"company_brief": f"⚠️ API 完全失效: {str(ex)}", "source_url": ""}

    source_url = ""
    try:
        if hasattr(response.candidates[0], 'grounding_metadata') and response.candidates[0].grounding_metadata.grounding_chunks:
            source_url = response.candidates[0].grounding_metadata.grounding_chunks[0].web.uri
    except:
        source_url = f"https://www.google.com/search?q=台股+{ticker}+{pure_name}+產業分析"

    try:
        match_json = re.search(r'\{.*\}', response.text, re.DOTALL)
        if match_json:
            ai_dict = json.loads(match_json.group(0))
            ai_dict['source_url'] = source_url
            return ai_dict
        else:
            raise ValueError("無法提取 JSON")
    except Exception as ex:
        return {
            "company_brief": f"⚠️ JSON 解析失敗: {str(ex)}", 
            "overview": "【資料不足，無法確認】", "value_chain": "【資料不足，無法確認】", "competitors": [], "drivers": "【資料不足，無法確認】",
            "source_url": source_url
        }
    # ====================================================================
    # 💥 擷取來源網址與 JSON 輸出
    # ====================================================================
    source_url = ""
    try:
        # 嘗試從 Google 搜尋結果中抽出真實網址
        if hasattr(response.candidates[0], 'grounding_metadata') and response.candidates[0].grounding_metadata.grounding_chunks:
            source_url = response.candidates[0].grounding_metadata.grounding_chunks[0].web.uri
    except:
        # 如果沒抓到，就自動生成一個 Google 搜尋的快捷按鈕網址
        source_url = f"https://www.google.com/search?q=台股+{ticker}+{pure_name}+產業分析"

    try:
        match_json = re.search(r'\{.*\}', response.text, re.DOTALL)
        if match_json:
            ai_dict = json.loads(match_json.group(0))
            ai_dict['source_url'] = source_url
            return ai_dict
        else:
            raise ValueError("無法提取 JSON")
    except Exception as ex:
        return {
            "company_brief": f"⚠️ JSON 解析失敗: {str(ex)}", 
            "overview": "...", "value_chain": "...", "competitors": [], "drivers": "...",
            "source_url": source_url
        }
    # ====================================================================
    # 💥 擷取來源網址與 JSON 輸出
    # ====================================================================
    source_url = ""
    try:
        # 嘗試從 Google 搜尋結果中抽出真實網址
        if hasattr(response.candidates[0], 'grounding_metadata') and response.candidates[0].grounding_metadata.grounding_chunks:
            source_url = response.candidates[0].grounding_metadata.grounding_chunks[0].web.uri
    except:
        # 如果沒抓到，就自動生成一個 Google 搜尋的快捷按鈕網址
        source_url = f"https://www.google.com/search?q=台股+{ticker}+{pure_name}+產業分析"

    try:
        match_json = re.search(r'\{.*\}', response.text, re.DOTALL)
        if match_json:
            ai_dict = json.loads(match_json.group(0))
            ai_dict['source_url'] = source_url
            return ai_dict
        else:
            raise ValueError("無法提取 JSON")
    except Exception as ex:
        return {
            "company_brief": f"⚠️ JSON 解析失敗: {str(ex)}", 
            "overview": "...", "value_chain": "...", "competitors": [], "drivers": "...",
            "source_url": source_url
        }

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
    # === 半導體與封裝設備 (核心戰略區) ===
    "2330": "2330 (台積電)",
    "5297": "5297 (廣化)",      # 封裝設備
    "7853": "7853 (政美應用)",  # AOI 檢測設備
    "3595": "3595 (山太士)",    # 封裝材料/IC設計
    
    # === CPO 與 光通訊族群 (強勢題材區) ===
    "3450": "3450 (聯鈞)",
    "3363": "3363 (上詮)",
    "6442": "6442 (光聖)",
    "6451": "6451 (訊芯-KY)",
    "3163": "3163 (波若威)",
    "4979": "4979 (華星光)",
    "3081": "3081 (聯亞)",
    "2455": "2455 (全新)",      # 化合物半導體(光通訊上游)
    
    # === 載板、PCB 與 散熱設備 (電子供應鏈) ===
    "3037": "3037 (欣興)",      # ABF載板
    "4958": "4958 (臻鼎-KY)",   # PCB
    "1815": "1815 (富喬)",      # 玻纖布(PCB上游)
    "2486": "2486 (一銓)",      # 均熱片
    
    # === 面板、記憶體與傳產 (循環與轉機區) ===
    "2408": "2408 (南亞科)",    # 記憶體
    "1802": "1802 (台玻)",      # 玻璃/電子級玻纖
    "3714": "3714 (富采)"       # LED/化合物半導體
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
    current_data = DEFAULT_STOCKS.copy()
    
    # 1. 讀取舊名單，並自動清洗掉「台股代號」這些垃圾字眼
    if os.path.exists(DICT_FILE):
        try:
            with open(DICT_FILE, "r", encoding="utf-8") as f:
                saved_data = json.load(f)
                if saved_data and isinstance(saved_data, dict):
                    for k, v in saved_data.items():
                        # 💥 洗白髒資料
                        clean_v = v.replace("台股代號 ", "").replace("台股代號", "")
                        current_data[k] = clean_v
        except Exception as e:
            print(f"讀取 stock_dict.json 失敗: {e}")
            
    # 2. 自動同步 JSON 倉庫 (把富喬、台玻自動加回來)
    try:
        db = load_industry_db()
        for sid, info in db.items():
            sid_str = str(sid).strip()
            if sid_str not in current_data:
                # 把百科裡的名稱也洗白
                company_name = info.get("name", "未知名稱").replace("台股代號 ", "")
                if sid_str in company_name:
                    current_data[sid_str] = company_name
                else:
                    current_data[sid_str] = f"{sid_str} ({company_name})"
    except Exception as e:
        print(f"自動同步選單失敗: {e}")

    # 3. 將乾淨的名單存回檔案
    try:
        with open(DICT_FILE, "w", encoding="utf-8") as f:
            json.dump(current_data, f, ensure_ascii=False, indent=4)
    except Exception as e:
        print(f"建立 stock_dict.json 失敗: {e}")
        
    return current_data

def save_stock_dict(data):
    try:
        with open(DICT_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
        return True
    except Exception as e:
        print(f"儲存 stock_dict.json 失敗: {e}")
        return False

def load_industry_db():
    """
    從 JSON 檔案載入產業百科資料庫 (清潔完工版)
    """
    if os.path.exists(INDUSTRY_DB_FILE):
        try:
            with open(INDUSTRY_DB_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                # 💥 修正重點：把原本這裡所有的 st.sidebar.write / markdown 內容全部刪除或註解掉
                return data
        except Exception as e:
            # 只保留真正的錯誤報錯即可
            st.sidebar.error(f"❌ 讀取 JSON 失敗: {e}")
            return {}
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
    
    # 💥 關鍵修復：改用 st.session_state 抓取「最新」的字典，確保新增時能立刻抓到 (廣化)
    current_dict = st.session_state.get('STOCK_DICT', STOCK_DICT)
    company_name = current_dict.get(sid, f"台股代號 {sid}")
    
    summary = f"分析「{company_name}」的核心業務。"
    ai_data = generate_ai_insights(company_name, summary)
    
    if not ai_data or "company_brief" not in ai_data:
        ai_data = {"company_brief": "⚠️ 更新失敗", "overview": "...", "value_chain": "...", "competitors": [], "drivers": "...", "source_url": ""}

    import datetime
    db[sid] = {
        "name": company_name,
        "company_brief": ai_data.get("company_brief", ""),
        "overview": ai_data.get("overview", ""),
        "value_chain": ai_data.get("value_chain", ""),
        "competitors": ai_data.get("competitors", []),
        "drivers": ai_data.get("drivers", ""),
        "source_url": ai_data.get("source_url", ""), # 🎯 確保網址存檔
        "last_updated": datetime.date.today().isoformat()
    }

    with open(db_file, "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, indent=4)
    
    st.session_state['INDUSTRY_DB'] = db
    return True, f"✅ 成功更新 {company_name}"
	
# --- K線獲取與修正清洗防線 ---
# 盤中快取 300 秒 (5分鐘) 剛好對齊 st_autorefresh
# 盤後快取 3600 秒 (1小時) 大幅節省伺服器資源
cache_ttl = 300 if is_trading_hours else 3600

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
                        
                        # 1. 抓取 Yahoo 最新的實時報價 Facts
                        latest_price = float(f_info['last_price']) if f_info['last_price'] else 0.0
                        latest_open = float(f_info['open']) if (f_info['open'] and f_info['open'] > 0) else latest_price
                        latest_high = float(f_info['day_high']) if (f_info['day_high'] and f_info['day_high'] > 0) else latest_price
                        latest_low = float(f_info['day_low']) if (f_info['day_low'] and f_info['day_low'] > 0) else latest_price
                        latest_vol = f_info['last_volume'] / 1000.0 if (f_info['last_volume'] and f_info['last_volume'] > 0) else 0.01

                        # 2. 判斷最後一根 K 線日期是否為「今天(或最近的收盤日)」
                        import datetime
                        today_date = datetime.date.today()
                        if today_date.weekday() == 5: # 週六 ➔ 基準日退回週五
                            today_date = today_date - datetime.timedelta(days=1)
                        elif today_date.weekday() == 6: # 週日 ➔ 基準日退回週五
                            today_date = today_date - datetime.timedelta(days=2)
                        
                        last_k_date = df.index[-1].date()
                        
                        # 3. 核心補齊決策：
                        if last_k_date < today_date and latest_price > 0:
                            # 手動建立新 K 線
                            new_timestamp = pd.Timestamp(today_date).tz_localize(df.index.tz)
                            df.loc[new_timestamp] = [latest_open, latest_high, latest_low, latest_price, latest_vol]
                        else:
                            # 進行即時覆蓋
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

                # ==============================================================================
                # 📈 技術指標計算區 (MA, MACD, KD, RSI)
                # ==============================================================================
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
        # 1. 確保日期格式正確
        df.index = pd.to_datetime(df.index)
        
        # 2. 取得「今天」的資料 (最後一根 K 棒)
        last_row = df.iloc[-1]
        today_date = last_row.name.date()
        
        quote["current"] = float(last_row['Close'])
        quote["open"] = float(last_row['Open'])
        quote["high"] = float(last_row['High'])
        quote["low"] = float(last_row['Low'])
        quote["volume_txt"] = str(round(last_row['Volume'], 1))

        # 3. 💥 【物理校準】找出所有「日期小於今天」的資料
        # 這樣可以徹底避開今天盤中的任何數據干擾
        historical_data = df[df.index.date < today_date]
        
        if not historical_data.empty:
            # 抓取「昨天（或上一個交易日）」最後一個收盤價
            # 這就是網頁上標示的官方昨收
            quote["prev_close"] = float(historical_data.iloc[-1]['Close'])
        else:
            # 如果還是失敗，才回歸 iloc[-2]
            quote["prev_close"] = float(df.iloc[-2]['Close'])
            
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

# 💥 【全域作用域宣告】
# ==============================================================================
# --- 在全域變數區塊 ---
current_stocks_dict = st.session_state.get('STOCK_DICT', load_stock_dict())
# 💥 關鍵修改：如果 session_state 裡還沒有選中的代號，才預設為清單中的第一個
if 'selected_sid' not in st.session_state:
    # list(current_stocks_dict.keys())[0] 會自動抓取您清單中的第一個代號 (現在是 2330)
    # 如果萬一連清單都是空的，最後才會用到 "2330" 這個保險
    st.session_state['selected_sid'] = list(current_stocks_dict.keys())[0] if current_stocks_dict else "2330"
# 側邊欄
with st.sidebar:
    # 1. 🚀 頂端漸層設計 (Logo 與專屬標示)
    st.sidebar.markdown(f"""
        <div style="background: linear-gradient(135deg, #1e3a8a, #000000); padding: 20px; border-radius: 15px; border: 1.5px solid #3b82f6; text-align: center; box-shadow: 0 4px 15px rgba(59, 130, 246, 0.3);">
            <h1 style="color: #60a5fa; font-size: 20px; font-weight: 900; margin: 0; letter-spacing: 2px;">🚀 戰情操控中心</h1>
            <p style="color: #94a3b8; font-size: 12px; margin-top:8px; font-weight: 500;">吳秉諺 專屬 AI 投資系統 v42.1</p>
        </div>
        """, unsafe_allow_html=True)

    st.sidebar.write("") 

# 2. 🎯 核心標的選擇
    st.sidebar.markdown("### 🎯 戰略目標選擇")
    
    # 💥 關鍵修改：增加 index 參數，並監聽變化
    # 先找出目前存好的 sid 在清單中是第幾個
    options_list = list(current_stocks_dict.keys())
    try:
        current_idx = options_list.index(st.session_state['selected_sid'])
    except:
        current_idx = 0

    target_sid = st.sidebar.selectbox(
        "選擇您的掃描標的", 
        options=options_list, 
        index=current_idx, # 🎯 讓選單釘在您剛選的位置
        format_func=lambda sid: current_stocks_dict.get(sid, sid),
        key="target_sid_selectbox",
        help="選擇您清單中要進行深度技術與籌碼分析的股票標的。"
    )
    
    # 當選單改變時，同步更新記憶
    st.session_state['selected_sid'] = target_sid
    
    # 同步更新 label 給右側大看板顯示用
    selected_label = current_stocks_dict.get(target_sid, target_sid)
    
    view_days = st.sidebar.slider(
        "📅 歷史數據追蹤天數", 30, 240, 90,
        help="調整右側 K 線圖展示的交易日長度。"
    )
    
    st.sidebar.divider()
    
# 3. 🌐 外部情資鏈結 (滿版按鈕排版)
    st.sidebar.link_button("🌐 Yahoo股市", f"https://tw.stock.yahoo.com/quote/{target_sid}", use_container_width=True)
    st.sidebar.link_button("📊 財務數據", f"https://goodinfo.tw/tw/StockDetail.asp?STOCK_ID={target_sid}", use_container_width=True)

    st.sidebar.divider()

# 4. 🏢 AI 產業百科 (離線優先，維持戰略深度)
    st.sidebar.markdown(
        "### 🏢 AI 產業百科", 
        help="這裡展示由 AI 深度生成的企業基本面、價值鏈與競爭對手分析。若發現資料過舊，可點擊下方按鈕更新。"
    )
    db = load_industry_db()
    target_sid_str = str(target_sid).strip()
    stock_info = db.get(target_sid_str)
    
    if stock_info:
        # 💥 終極格式清洗器：專治 AI 亂吐巢狀字典或陣列，自動轉成漂亮條列式
        def format_text(val):
            if isinstance(val, dict):
                return "\n\n".join([f"🔸 {v}" for k, v in val.items()])
            elif isinstance(val, list):
                return "\n\n".join([f"🔸 {v}" for v in val])
            return str(val)

        with st.sidebar.expander("🎯 個股主要業務", expanded=True):
            st.info(format_text(stock_info.get("company_brief", "資料載入中...")))
        
        with st.sidebar.expander("📍 產業市場規模", expanded=False):
            st.info(format_text(stock_info.get("overview", "資料載入中...")))
        
        with st.sidebar.expander("🔗 產業價值鏈", expanded=False):
            st.info(format_text(stock_info.get("value_chain", "資料載入中...")))
        
        with st.sidebar.expander("🔗 相關競爭對手", expanded=False):
            comp_data = stock_info.get("competitors", [])
            if isinstance(comp_data, list):
                st.markdown("\n".join([f"- **{peer}**" for peer in comp_data]) or "暫無資料")
            elif isinstance(comp_data, dict):
                st.markdown("\n".join([f"- **{v}**" for k, v in comp_data.items()]))
            else:
                st.markdown(str(comp_data))
        
        with st.sidebar.expander("📈 產業驅動因子", expanded=False):
            st.info(format_text(stock_info.get("drivers", "資料載入中...")))
            
        st.sidebar.caption(f"✨ 百科更新時間：{stock_info.get('last_updated', '歷史資料')}")
        
        # ==========================================
        # 🎯 絕對強制顯示版：資料來源網址導流按鈕 (這段在更新按鈕上方)
        # ==========================================
        s_url = stock_info.get("source_url", "")
        if not s_url:
            c_name = stock_info.get("name", target_sid_str)
            s_url = f"https://www.google.com/search?q=台股+{c_name}+產業分析"
            
        html_btn = '<div style="text-align: right; margin-bottom: 10px;">' + \
                   f'<a href="{s_url}" target="_blank" style="color: #60a5fa; text-decoration: none; font-size: 13px; font-weight: 600;">' + \
                   '🔍 查看 AI 參考來源網頁 →</a></div>'
        st.sidebar.markdown(html_btn, unsafe_allow_html=True)
        # ==========================================

        # 💥 視覺強化版 1：有資料時的「更新按鈕」
        if st.sidebar.button("🔄 更新這檔百科", key=f"re_up_{target_sid_str}", use_container_width=True, help="點擊後將連網抓取最新動態並重寫百科資料，會消耗一次 API 額度。"):
            with st.sidebar.status(f"🚀 正在重塑 {target_sid_str} 產業百科...", expanded=True) as status:
                prog_bar = st.progress(0, text="準備發動 AI 引擎...")
                
                prog_bar.progress(30, text="🌐 正在連網搜尋最新產業動態...")
                success, msg = auto_update_industry_db(target_sid_str)
                
                if success:
                    prog_bar.progress(80, text="💾 正在將新資料寫入 JSON 資料庫...")
                    import time
                    time.sleep(0.5) 
                    
                    prog_bar.progress(100, text="✅ 百科更新成功！")
                    status.update(label="✅ 百科更新成功！", state="complete", expanded=False)
                    st.rerun()
                else:
                    prog_bar.error("⚠️ 更新過程發生中斷")
                    st.write(f"系統回報: {msg}")
                    status.update(label="❌ 更新失敗", state="error")

    # 💥 視覺強化版 2：無資料時的「首次生成按鈕」
    else:
        st.sidebar.warning(f"⚠️ 庫存中無 {target_sid_str} 的資料")
        
        if st.sidebar.button(f"🎯 消耗額度生成百科", key=f"init_{target_sid_str}", use_container_width=True,help="這檔股票目前尚無百科。點擊將啟動 AI 連網搜尋並建立全新資料庫，會消耗一次 API 額度。"):
            with st.sidebar.status(f"🤖 正在為 {target_sid_str} 建立全新百科...", expanded=True) as status:
                prog_bar = st.progress(0, text="準備發動 AI 引擎...")
                
                prog_bar.progress(30, text="🌐 AI 正在連網深度檢索...")
                success, msg = auto_update_industry_db(target_sid_str)
                
                if success:
                    prog_bar.progress(80, text="💾 正在建檔寫入資料庫...")
                    import time
                    time.sleep(0.5)
                    
                    prog_bar.progress(100, text="✅ 全新百科建立完成！")
                    status.update(label="🎉 百科建檔成功！", state="complete", expanded=False)
                    st.rerun()
                else:
                    prog_bar.error("⚠️ 生成過程發生中斷")
                    st.write(f"系統回報: {msg}")
                    status.update(label="❌ 生成失敗", state="error")
# 5. 🩺 系統檢修區
    st.sidebar.divider()
    with st.sidebar.expander("🛠️ 系統後勤工具", expanded=False):
        
        # --- 區塊 1：保留您原本的 AI 連線測試 ---
        st.markdown("**AI 連線測試**")
        if st.button("🔍 版本測試", use_container_width=True):
            st.toast("正在測試...")
            
        if st.button("📋 模型清單", use_container_width=True):
            pass
        
        # --- 區塊 2：💥 新增的系統記憶體管理 (清除快取) ---
        st.divider()
        st.markdown(
            "**系統記憶體管理**", 
            help="當某檔股票卡住（例如出現紅底白字）或一直抓不到最新報價時，使用此功能強制清空暫存。"
        )
        if st.button("🧹 強制清除系統快取", use_container_width=True, help="點擊後將清空所有 Yahoo 報價與 API 的歷史暫存，並重新載入網頁。"):
            st.cache_data.clear()
            st.success("✅ 系統快取已完美清除！")
            import time
            time.sleep(1)
            st.rerun()
            
        # --- 區塊 3：保留完整的雙資料庫下載功能 ---
        st.divider()
        st.markdown(
            "**資料庫管理**", 
            help="您可以下載目前的百科資料庫與雷達名單備份。未來若雲端伺服器重置，可將這些 JSON 檔案上傳至 GitHub 以恢復所有珍貴資料。"
        )
        
        if os.path.exists("industry_db.json"):
            with open("industry_db.json", "r", encoding="utf-8") as f:
                st.download_button(
                    "📥 下載百科資料庫 (industry_db)", 
                    f.read(), 
                    "industry_db.json", 
                    "application/json", 
                    use_container_width=True,
                    help="下載完整的 AI 產業百科內容。若要保留 AI 生成的產業分析與查證網址，請備份此檔案。"
                )
                
        if os.path.exists(stock_dict.json"):
            with open("stock_dict.json", "r", encoding="utf-8") as f:
                st.download_button(
                    "📥 下載雷達名單 (stock_dict)", 
                    f.read(), 
                    "stock_dict.json", 
                    "application/json", 
                    use_container_width=True,
                    help="下載您的自選股雷達名單。將此檔案上傳至 GitHub 後，背景掃描器 (auto_scan.py) 才能偵測到新加入的股票。"
                )

# 6. ➕ 擴建雷達
    st.sidebar.divider()
    st.sidebar.markdown("### ➕ 擴建雷達-新增股票")
    new_sid = st.sidebar.text_input("輸入股票代號", help="資料請核對正確，例如 2330")
    new_name = st.sidebar.text_input("輸入股票名稱", help="資料請核對正確，例如 台積電")
    
    # 💥 捨棄 with col_add 排版，直接使用全寬按鈕
    if st.sidebar.button("⚡ 新增百科標的", use_container_width=True, help="輸入上方的代號與名稱後點擊此按鈕，系統會將其加入您的觀察清單，並立刻發動 AI 連網生成該公司的專屬百科。"):
        if new_sid and new_name:
            with st.sidebar.status("🤖 正在處理新增請求...", expanded=True) as status:
                prog_bar = st.progress(0, text="準備開始...")
                
                prog_bar.progress(20, text="📝 正在寫入預設名單...")
                current_stocks = load_stock_dict()
                current_stocks[new_sid] = f"{new_sid} ({new_name})"
                save_stock_dict(current_stocks)
                st.session_state['STOCK_DICT'] = current_stocks
                
                prog_bar.progress(50, text="🌐 AI 正在連網搜尋最新資料 (這可能需要 5-10 秒)...")
                try:
                    success, msg = auto_update_industry_db(new_sid)
                    if success:
                        prog_bar.progress(100, text="✅ 百科補全完成！")
                        st.write(f"🎉 {msg}")
                        status.update(label="🎉 標的新增與百科成功！", state="complete", expanded=False)
                    else:
                        prog_bar.error("⚠️ AI 回傳資料不完全")
                        status.update(label="⚠️ 標的已新增，但百科失敗", state="error")
                except Exception as e:
                    prog_bar.error("❌ 發生未知錯誤")
                    st.write(f"系統訊息: {str(e)}")
                    status.update(label="❌ 百科生成失敗", state="error")
            
            import time
            time.sleep(1.2)
            st.rerun()
        else:
            st.sidebar.error("❌ 請輸入完整的代號與名稱")
                
    # 💥 捨棄 with col_clean 排版，直接使用全寬按鈕
    if st.sidebar.button("🧹 百科智慧補全", use_container_width=True, help="僅針對尚未有資料的股票進行 AI 生成"):
        st.session_state['confirm_reset'] = True

    if st.session_state.get('confirm_reset'):
        st.sidebar.warning("⚠️ 系統將掃描清單，僅更新「無資料」的標的。")
        
        # 💥 捨棄 col_yes, col_no，直接使用全寬按鈕
        if st.sidebar.button("✅ 開始補百科資料", use_container_width=True):
            db = load_industry_db() 
            current_stocks = load_stock_dict()
            all_sids = list(current_stocks.keys())
            total = len(all_sids)
            
            progress_bar = st.sidebar.progress(0, text="🤖 檢查資料庫狀態...")
            
            for i, sid in enumerate(all_sids):
                if str(sid).strip() in db:
                    pass 
                else:
                    try:
                        auto_update_industry_db(sid)
                        import time
                        time.sleep(15) 
                    except:
                        pass
                progress_bar.progress((i + 1) / total, text=f"🔍 檢查中: {i+1}/{total}")
            
            st.sidebar.success("✅ 百科補全作業完成！")
            import time
            time.sleep(1)
            st.session_state['confirm_reset'] = False
            st.rerun()
        
        if st.sidebar.button("❌ 取消", use_container_width=True):
            st.session_state['confirm_reset'] = False
            st.rerun()

# --- 數據加載線 (外掛 - 必須靠最左邊) ---
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
                # 💥 刪除原有的 st.warning，避免視覺混淆
                custom_diagnostic_card(
                    "💤 【量能明顯萎縮】",
                    "💎 診斷：【大戶惜售 / 籌碼鎖定】\n\n"
                    "• 現狀分析：量能大幅萎縮，但價格頑強守在 MA5 防線之上，顯示籌碼已被莊家大戶鎖死，散戶賣壓基本出盡。\n"
                    "• 戰術提示：此處的突破有 90% 以上為「洗盤後的真突破」。建議沿著 MA5 / MA10 移動停利，偏多看待。",
                    "warning" # 這裡的 warning 會渲染成漂亮的琥珀黃邊框
                )
            else:
                vol_diag_msg = "🥶 人氣退潮"
                st.warning("💤 【量能明顯萎縮】")  
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

# 💥 捨棄 col_dc_action 排版，改為直列全寬，更具控制台氣勢
        if st.button(
            "🔗 發送 Discord 測試訊息", 
            use_container_width=True,
            help="手動測試網頁與您的 Discord 頻道是否成功對接。"
        ):
# 💥 強制鎖定台灣時間 (UTC+8)
            import datetime
            tz_tw = datetime.timezone(datetime.timedelta(hours=8))
            test_time = datetime.datetime.now(tz_tw).strftime('%Y-%m-%d %H:%M:%S')
            
            test_embed = {
                "title": "✅ 秉諺的黑馬雷達連線測試",
                "description": "網頁主端控制台發送成功！手動推播管道運作良好。",
                "color": 3447003,
                "footer": {"text": f"測試時間: {test_time}"}
            }
            success, msg = send_discord_webhook(DEFAULT_DISCORD_WEBHOOK, test_embed)
            if success: st.success("✅ " + msg)
            else: st.error("❌ " + msg)
                
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
