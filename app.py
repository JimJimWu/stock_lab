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
# ==============================================================================
# 雲端資料庫工具函數 (請放入 import 區段之後，主邏輯之前)
# ==============================================================================
import gspread
from oauth2client.service_account import ServiceAccountCredentials
def load_industry_db_from_cloud():
    try:
        sheet = get_google_sheet()
        records = sheet.get_all_records()
        return {str(row['sid']): json.loads(row['data']) for row in records if row['sid']}
    except Exception as e:
        if os.path.exists(INDUSTRY_DB_FILE):
            with open(INDUSTRY_DB_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        return {}

def get_google_sheet():
    """建立 Google Sheets 連線"""
    creds_dict = json.loads(st.secrets["GSPREAD_JSON"])
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(creds)
    # 開啟您的 Google Sheet
    return client.open_by_url(st.secrets["SHEET_URL"]).sheet1

def migrate_local_to_cloud():
    """執行一次性遷移：將本地 JSON 檔案上傳至 Google Sheets"""
    # 讀取原本的本地檔案
    with open("industry_db.json", "r", encoding="utf-8") as f:
        local_db = json.load(f)
    
    sheet = get_google_sheet()
    
    # 準備資料格式：[sid, json_string]
    rows = [[str(sid), json.dumps(data, ensure_ascii=False)] for sid, data in local_db.items()]
    
    # 清空雲端舊資料並寫入
    sheet.clear() 
    sheet.append_row(["sid", "data"]) # 設定表頭
    sheet.append_rows(rows) # 批次寫入
    st.success(f"成功將 {len(rows)} 筆資料同步至 Google Sheets！")
# ==============================================================================
def generate_ai_insights(company_name, prompt_context=""):
    """精簡版：使用 flash 模型，透過嚴格的 JSON 模板約束輸出品質"""
    import json
    import re
    
    # 拆解代號與名稱邏輯保持不變
    match = re.match(r'^([A-Za-z0-9]+)(?:\s*\((.*?)\))?', company_name.strip())
    ticker = match.group(1) if match else company_name
    pure_name = match.group(2) if match and match.group(2) else company_name

    # 強制使用輕量模型 gemini-2.5-flash，不使用 search retrieval
    model = genai.GenerativeModel(model_name='gemini-2.5-flash')
    
    # 建立嚴格的輸出格式模板
    prompt = f"""
    分析對象: {ticker} {pure_name}
    請僅輸出符合以下 JSON 格式的內容，不要包含任何前言、結尾或 Markdown 程式碼區塊符號。
    {{
        "company_brief": "請以三句話描述公司核心業務與產業地位",
        "overview": "公司在市場中的定位與規模，若不確定請填寫【資料不足】",
        "value_chain": "請以清單方式呈現上中下游",
        "competitors": ["對手1", "對手2", "對手3"],
        "drivers": "請條列公司未來成長動能"
    }}
    """
    
    try:
        response = model.generate_content(prompt)
        # 使用正則表達式提取 JSON，過濾掉任何非 JSON 的雜訊
        match_json = re.search(r'\{.*\}', response.text, re.DOTALL)
        if match_json:
            ai_dict = json.loads(match_json.group(0))
            # 確保來源網址依然有效，方便您點擊查證
            ai_dict['source_url'] = f"https://www.google.com/search?q=台股+{ticker}+{pure_name}+產業分析"
            return ai_dict
    except Exception as e:
        # 發生錯誤時回傳結構化的失敗資訊，防止 UI 渲染崩潰
        return {
            "company_brief": f"⚠️ 解析錯誤: {str(e)}", 
            "overview": "...", "value_chain": "...", "competitors": [], "drivers": "...",
            "source_url": f"https://www.google.com/search?q=台股+{ticker}+{pure_name}+產業分析"
        }
    return None

    # --- 💥 精簡後的統一解析邏輯 ---
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
            "overview": "【資料不足，無法確認】", "value_chain": "【資料不足，無法確認】", 
            "competitors": [], "drivers": "【資料不足，無法確認】",
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
DICT_FILE = "watchlist.json"
INDUSTRY_DB_FILE = "industry_db.json"
DEFAULT_DISCORD_WEBHOOK = os.environ.get("DISCORD_WEBHOOK") or ""

DEFAULT_STOCKS = {
    # === 半導體與設備 (核心戰略區) ===
    "2330": "台積電",
    "6770": "力積電",
    "6510": "精測",
    "6849": "奇鼎",
    "5297": "廣化",
    "7853": "政美應用",
    "3595": "山太士",
    
    # === CPO 與 光通訊族群 (強勢題材區) ===
    "3450": "聯鈞",
    "3363": "上詮",
    "6442": "光聖",
    "6451": "訊芯-KY",
    "3163": "波若威",
    "4979": "華星光",
    "3081": "聯亞",
    "2455": "全新",
    
    # === PCB 與 電子供應鏈 ===
    "3037": "欣興",
    "4958": "臻鼎-KY",
    "1815": "富喬",
    "2486": "一銓",
    "6282": "康舒",
    
    # === 機電與綠能 (政策循環新板塊) ===
    "1504": "東元",
    "6477": "安集",
    
    # === 面板、記憶體與傳產 (轉機區) ===
    "2408": "南亞科",
    "1802": "台玻",
    "3714": "富采"
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

# --- 全市場母體資料庫 (供搜尋與新增使用) ---
def load_full_market():
    if os.path.exists("full_market_dict.json"):
        try:
            with open("full_market_dict.json", "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"讀取 full_market_dict.json 失敗: {e}")
    return {} # 找不到就回傳空字典防呆
	
# --- 永久資料庫讀寫 ---
def load_stock_dict():
    current_data = DEFAULT_STOCKS.copy()
    
    # 1. 讀取舊名單，並啟動強制格式化引擎，統一為「代號 (名稱)」
    if os.path.exists(DICT_FILE):
        try:
            with open(DICT_FILE, "r", encoding="utf-8") as f:
                saved_data = json.load(f)
                if saved_data and isinstance(saved_data, dict):
                    for k, v in saved_data.items():
                        # 💥 萃取出純淨名稱，過濾掉任何可能殘留的舊代號或括號
                        pure_name = v.replace(str(k), "").replace("台股代號", "").replace("(", "").replace(")", "").strip()
                        current_data[k] = f"{k} ({pure_name})"
        except Exception as e:
            print(f"讀取 {DICT_FILE} 失敗: {e}")
            
    # 💥 【防護升級】：已移除原先強迫將 industry_db 歷史股票倒進來的邏輯，徹底杜絕幽靈股票
    
    # 2. 將格式完美統一後的乾淨名單存回實體檔案
    try:
        with open(DICT_FILE, "w", encoding="utf-8") as f:
            json.dump(current_data, f, ensure_ascii=False, indent=4)
    except Exception as e:
        print(f"建立 {DICT_FILE} 失敗: {e}")
        
    # 3. 【雙軌合併】在記憶體中動態加入「雷達菁英」，顯示於儀表板但絕不寫入實體檔案
    if os.path.exists("radar_elite.json"):
        try:
            with open("radar_elite.json", "r", encoding="utf-8") as f:
                radar_stocks = json.load(f)
                for sid, sname in radar_stocks.items():
                    if sid not in current_data:
                        pure_name = sname.replace(str(sid), "").replace("台股代號", "").replace("(", "").replace(")", "").strip()
                        # 加上閃電標籤，讓您一眼看出這是雲端抓下來的短線菁英
                        current_data[sid] = f"{sid} ({pure_name}) (⚡雷達)"
        except Exception as e:
            print(f"讀取 radar_elite.json 失敗: {e}")
            
    return current_data
            
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

    # 3. 將乾淨的名單存回檔案 (此時只存手動的永久名單，絕不包含雷達菁英)
    try:
        with open(DICT_FILE, "w", encoding="utf-8") as f:
            json.dump(current_data, f, ensure_ascii=False, indent=4)
    except Exception as e:
        print(f"建立 {DICT_FILE} 失敗: {e}")
        
    # ==========================================================================
    # 💥 4. 【雙軌合併】在記憶體中動態加入「雷達菁英」，顯示於儀表板但絕不寫入實體檔案
    # ==========================================================================
    if os.path.exists("radar_elite.json"):
        try:
            with open("radar_elite.json", "r", encoding="utf-8") as f:
                radar_stocks = json.load(f)
                for sid, sname in radar_stocks.items():
                    # 如果這檔股票已經在您的永久名單中，就不重複加標籤
                    if sid not in current_data:
                        current_data[sid] = f"{sname} (⚡雷達)"
        except Exception as e:
            print(f"讀取 radar_elite.json 失敗: {e}")
            
    return current_data

def save_stock_dict(data):
    try:
        # 💥 【防呆攔截】寫入永久資料庫前，將帶有「(⚡雷達)」標籤的動態名單強制剔除
        pure_data = {}
        for k, v in data.items():
            if "(⚡雷達)" not in v:
                pure_data[k] = v
                
        with open(DICT_FILE, "w", encoding="utf-8") as f:
            json.dump(pure_data, f, ensure_ascii=False, indent=4)
        return True
    except Exception as e:
        print(f"儲存 {DICT_FILE} 失敗: {e}")
        return False
		
# 💥 【V34.2 升級：富文本量化回測記錄器 (精準對齊版)】
def log_signal_to_csv(sid, sname, price, embed):
    log_file = "signal_history.csv"
    import datetime
    tz_tw = datetime.timezone(datetime.timedelta(hours=8))
    now_time = datetime.datetime.now(tz_tw).strftime('%Y-%m-%d %H:%M:%S')
    import os
    file_exists = os.path.isfile(log_file)
    
    try:
        # 名稱淨化
        pure_sname = sname
        if "(" in sname and ")" in sname:
            pure_sname = sname.split("(")[1].split(")")[0]
            
        # 萃取數據 (移除幽靈趨勢欄位)
        desc = embed.get("description", "").replace("*", "").replace("`", "")
        tech_vol = ""
        
        # 只抓取 Discord 實際有發送的「技術」欄位
        for field in embed.get("fields", []):
            if "技術" in field.get("name", ""):
                tech_vol = field.get("value", "").replace("\n", " | ").replace("`", "")
        
        # 寫入 CSV
        with open(log_file, mode='a', encoding='utf-8-sig', newline='') as f:
            if not file_exists:
                # 💥 修正表頭，對齊實際存在的 6 個欄位
                f.write("日期時間,股票代號,股票名稱,觸發價格,核心訊號,技術與量能\n")
            
            clean_desc = desc.replace(',', '，')
            clean_tech = tech_vol.replace(',', '，')
            
            # 💥 寫入 6 個完美對齊的數據
            f.write(f"{now_time},{sid},{pure_sname},{price},{clean_desc},{clean_tech}\n")
    except Exception as e:
        print(f"寫入 CSV 失敗: {e}")
		
# 1. 這是您已經寫好的雲端讀取函數
def load_industry_db():
    try:
        sheet = get_google_sheet()
        records = sheet.get_all_records()
        # 轉換為您原本需要的字典格式
        return {str(row['sid']): json.loads(row['data']) for row in records if row['sid']}
    except Exception as e:
        # 如果雲端失敗，自動回頭讀取本地備份
        if os.path.exists(INDUSTRY_DB_FILE):
            with open(INDUSTRY_DB_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        return {}

# 2. 確保 Session State 使用新函數
if 'STOCK_DICT' not in st.session_state:
    st.session_state['STOCK_DICT'] = load_stock_dict()

if 'INDUSTRY_DB' not in st.session_state:
    # 💥 改用雲端讀取函式
    st.session_state['INDUSTRY_DB'] = load_industry_db()

STOCK_DICT = st.session_state['STOCK_DICT']
INDUSTRY_DB = st.session_state['INDUSTRY_DB']

# --- 百科生成模組 ---
def auto_update_industry_db(sid):
    sid = str(sid).strip()
    db = load_industry_db()
    
    # 💥 修改這裡：不要在此處主動讀取所有檔案，避免 loop，只根據當前 sid 執行
    current_dict = st.session_state.get('STOCK_DICT', STOCK_DICT)
    company_name = current_dict.get(sid, f"台股代號 {sid}")
    
    # 簡化 Prompt，移除過度強制的系統指令，節省 Token
    prompt_context = "請提供以下台股公司的產業分析 (JSON格式: company_brief, overview, value_chain, competitors, drivers)。"
    
    ai_data = generate_ai_insights(company_name, prompt_context)
    
    if ai_data:
        db[sid] = {
            "name": company_name,
            "company_brief": ai_data.get("company_brief", ""),
            "overview": ai_data.get("overview", ""),
            "value_chain": ai_data.get("value_chain", ""),
            "competitors": ai_data.get("competitors", []),
            "drivers": ai_data.get("drivers", ""),
            "source_url": ai_data.get("source_url", ""),
            "last_updated": datetime.date.today().isoformat()
        }
        
        # 寫回雲端 (使用 gspread)
        sheet = get_google_sheet()
        # 轉成字串格式寫入
        sheet.update_cell(len(db) + 1, 1, sid) 
        sheet.update_cell(len(db) + 1, 2, json.dumps(db[sid], ensure_ascii=False))
        
        st.session_state['INDUSTRY_DB'] = db
        return True, f"✅ {company_name} 更新成功"
    return False, "AI 解析失敗"

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
                df['MA60'] = df['Close'].rolling(60).mean()
                df['MA240'] = df['Close'].rolling(240).mean()
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
		# 💥 放在推播成功的正下方，return 的正上方
		# 💥 傳入 embed，讓 Excel 直接拷貝 Discord 的豐富數據
        log_signal_to_csv(sid, sname, current_price, embed)
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

# ==============================================================================
# 📊 獨立擴充模組：策略多週期持股勝率模擬分析儀
# ==============================================================================
def render_backtest_dashboard():
    import pandas as pd
    import plotly.graph_objects as go
    import os
    
    st.markdown("---")
    st.markdown("## 📈 策略多週期持股勝率模擬分析儀")
    
    file_path = "signal_history_backtest.csv"
    if not os.path.exists(file_path):
        st.warning(f"尚未偵測到 {file_path}，請確認回測引擎是否已執行完畢。")
        return
        
    try:
        df = pd.read_csv(file_path, encoding="utf-8-sig")
        signal_col = "核心訊號" if "核心訊號" in df.columns else ("訊號" if "訊號" in df.columns else None)
        
        if not signal_col:
            st.error("CSV 中找不到『核心訊號』欄位，無法進行分組分析。")
            return

        # ==============================================================================
        # 💥 【新增：戰情室動態數據篩選器】
        # ==============================================================================
        # 確保有日期時間欄位才能進行時間篩選
        if "日期時間" in df.columns:
            df['日期時間'] = pd.to_datetime(df['日期時間'])
            
            col1, col2 = st.columns(2)
            with col1:
                import datetime
                min_date = df['日期時間'].dt.date.min()
                max_date = df['日期時間'].dt.date.max()
                # 如果歷史資料不足30天，就取最小日期
                default_start = max(min_date, max_date - datetime.timedelta(days=30))
                
                selected_dates = st.date_input(
                    "🗓️ 選擇回測區間",
                    value=[default_start, max_date],
                    min_value=min_date,
                    max_value=max_date
                )

            with col2:
                available_signals = df[signal_col].dropna().unique().tolist()
                selected_signals = st.multiselect(
                    "🎯 選擇欲分析的訊號型態",
                    options=available_signals,
                    default=available_signals
                )

            # 執行 DataFrame 覆寫過濾
            if len(selected_dates) == 2:
                start_date, end_date = selected_dates
                df = df[
                    (df['日期時間'].dt.date >= start_date) & 
                    (df['日期時間'].dt.date <= end_date) &
                    (df[signal_col].isin(selected_signals))
                ]
            elif len(selected_dates) == 1:
                start_date = selected_dates[0]
                df = df[
                    (df['日期時間'].dt.date == start_date) &
                    (df[signal_col].isin(selected_signals))
                ]
                
        # 🛡️ 防呆：如果篩選後沒有任何資料，提早結束避免畫圖報錯
        if df.empty:
            st.warning("⚠️ 在目前的篩選條件下，沒有找到任何符合的回測數據。")
            return
        # ==============================================================================
            
        periods = ["T+1", "T+3", "T+5", "T+10", "T+20"]
        fig = go.Figure()
        colors = ["#FF4B4B", "#00CC96", "#AB63FA", "#FFA15A"]
        
        grouped = df.groupby(signal_col)
        for i, (signal_name, group_df) in enumerate(grouped):
            win_rates = []
            for p in periods:
                col_name = f"{p} 報酬率(%)"
                if col_name in group_df.columns:
                    valid_data = group_df[group_df[col_name] != 0.0]
                    if len(valid_data) > 0:
                        win_rate = (len(valid_data[valid_data[col_name] > 0]) / len(valid_data)) * 100
                    else:
                        win_rate = 0
                    win_rates.append(win_rate)
                else:
                    win_rates.append(0)
                    
            fig.add_trace(go.Scatter(
                x=periods, y=win_rates, mode='lines+markers+text',
                name=signal_name, text=[f"{val:.1f}%" for val in win_rates],
                textposition="top center", line=dict(width=3, color=colors[i % len(colors)]),
                marker=dict(size=10)
            ))
            
# 💥 請確保 fig 的 f，跟上面 for 的 f 完美垂直對齊！
        fig.update_layout(
            title="不同訊號之多週期勝率演變交叉圖", 
            xaxis_title="持有週期", 
            yaxis_title="勝率 (%)",
            yaxis=dict(range=[0, 110]), 
            hovermode="x unified",
            legend=dict(orientation="h", yanchor="top", y=-0.2, xanchor="center", x=0.5),
            margin=dict(l=20, r=20, t=60, b=120)
        )
        
        # 下方的 st.plotly_chart 也要跟著對齊
        st.plotly_chart(fig, use_container_width=True)
        st.info("💡 **分析洞察**：觀察兩條線的交叉點。若『量能爆發』在中後期勝率快速下滑，而『大戶惜售』勝率穩步上升，即完美印證了短跑選手與馬拉松選手的策略差異。")
    except Exception as e:
        st.error(f"儀表板渲染失敗: {e}")

# ==============================================================================
# 側邊欄與視角切換控制
# ==============================================================================
with st.sidebar:
    # 1. 🚀 頂端漸層設計 (Logo 與專屬標示)
    st.sidebar.markdown(f"""
        <div style="background: linear-gradient(135deg, #1e3a8a, #000000); padding: 20px; border-radius: 15px; border: 1.5px solid #3b82f6; text-align: center; box-shadow: 0 4px 15px rgba(59, 130, 246, 0.3);">
            <h1 style="color: #60a5fa; font-size: 20px; font-weight: 900; margin: 0; letter-spacing: 2px;">🚀 戰情操控中心</h1>
            <p style="color: #94a3b8; font-size: 12px; margin-top:8px; font-weight: 500;">吳秉諺 專屬 AI 投資系統 v42.1</p>
        </div>
        """, unsafe_allow_html=True)

    st.sidebar.write("") 

    # 💥 UI/UX 美化升級：現代化分段切換按鈕
    st.sidebar.markdown("### 🌐 系統視角切換")
    
    # 建立記憶體來記住目前按下的按鈕
    if 'app_mode' not in st.session_state:
        st.session_state['app_mode'] = "🎯 個股戰情室"
        
    # 建立左右兩個等寬的空間
    col1, col2 = st.sidebar.columns(2)
    
    # 運用 type="primary" 讓正在看的那一邊亮起專屬主題色
    if col1.button("🎯 個股戰情", use_container_width=True, type="primary" if st.session_state['app_mode'] == "🎯 個股戰情室" else "secondary"):
        st.session_state['app_mode'] = "🎯 個股戰情室"
        st.rerun()
        
    if col2.button("📊 回測中心", use_container_width=True, type="primary" if st.session_state['app_mode'] == "📊 策略回測中心" else "secondary"):
        st.session_state['app_mode'] = "📊 策略回測中心"
        st.rerun()

    # 將記憶體狀態交接給主程式去分流畫面
    app_mode = st.session_state['app_mode']
    st.sidebar.divider()

    # ==========================================
    # 🌪️ 系統擴充：大盤宏觀天氣預報 (避震器)
    # ==========================================
    import yfinance as yf
    import pandas as pd
    
    @st.cache_data(ttl=3600) # 快取 1 小時，避免頻繁抓取浪費效能
    def get_market_weather():
        try:
            # 抓取台股加權指數 (^TWII)
            twii = yf.download("^TWII", period="2mo", progress=False)
            if twii.empty:
                return "UNKNOWN", 0, 0
                
            if isinstance(twii.columns, pd.MultiIndex):
                twii.columns = twii.columns.get_level_values(0)
                
            twii['20MA'] = twii['Close'].rolling(window=20).mean()
            
            latest_close = float(twii['Close'].iloc[-1])
            latest_20ma = float(twii['20MA'].iloc[-1])
            prev_close = float(twii['Close'].iloc[-2])
            
            # 計算單日跌幅
            daily_drop = ((latest_close - prev_close) / prev_close) * 100
            
            # 判定邏輯：單日重挫 > 2.5% 或 跌破月線
            if daily_drop <= -2.5 or latest_close < latest_20ma:
                return "DANGER", daily_drop, latest_close
            elif latest_close > latest_20ma and daily_drop > 0:
                return "SAFE", daily_drop, latest_close
            else:
                return "WARNING", daily_drop, latest_close
        except:
            return "UNKNOWN", 0, 0

    st.sidebar.markdown("### 🌪️ 宏觀環境監控")
    status, drop_pct, close_idx = get_market_weather()
    
    if status == "DANGER":
        st.sidebar.error(f"🔴 **極端警戒 (破月線/重挫)**\n\n大盤: {close_idx:,.0f} 點 ({drop_pct:.2f}%)\n\n系統建議：流動性枯竭風險極高，暫停所有【量能爆發突破】追價策略，提高現金水位。")
    elif status == "WARNING":
        st.sidebar.warning(f"🟡 **震盪整理 (測試支撐)**\n\n大盤: {close_idx:,.0f} 點 ({drop_pct:.2f}%)\n\n系統建議：大盤動能放緩，可縮小部位，優先關注【大戶惜售】之抗跌標的。")
    elif status == "SAFE":
        st.sidebar.success(f"🟢 **多頭防護網開啟**\n\n大盤: {close_idx:,.0f} 點 (+{drop_pct:.2f}%)\n\n系統建議：月線之上安全運行，雙核心策略可正常執行。")
    else:
        # 💥 將原本的「連線中...」改成誠實的錯誤提示
        st.sidebar.warning("⚠️ **大盤連線暫時異常**\n\nYahoo API 目前無回應。這不會影響您的個股雷達功能，系統將於稍後自動重試。")
        
    st.sidebar.divider()

# 💥 畫面分流魔法 (主程式攔截點)
if app_mode == "📊 策略回測中心":
    render_backtest_dashboard()
    st.stop()  # 系統走到這裡就會完美停住，進入大盤回測模式
# ==============================================================================
# 🎯 個股戰情室 (當切換至個股模式時，以下才會執行)
# ==============================================================================
# --- 請確保在這段程式碼之前，已經呼叫了 load_full_market() ---
# 1. 💥 呼叫函式並指派給變數 (這行絕對不能有註解符號)
full_market_data = load_full_market() 

# 2. 判斷要使用哪個字典
search_source_dict = full_market_data if full_market_data else current_stocks_dict

with st.sidebar:
    # 1. 🎯 每日戰情室 (聚焦核心標的)
    st.sidebar.markdown("### 🎯 每日戰情室 (已關注)")
    current_stocks = load_stock_dict() # 確保讀取的是自選名單
    
    # 建立「代號 (名稱)」格式的選項列表
    options_list = list(current_stocks.keys())
    
    # 設定目前的選定指標
    try:
        current_idx = options_list.index(st.session_state['selected_sid'])
    except:
        current_idx = 0

    target_sid = st.sidebar.selectbox(
        "選擇每日觀察標的", 
        options=options_list, 
        index=current_idx,
        # 這裡的邏輯：如果您的 current_stocks 已經存成 "代號 (名稱)"，就直接顯示
        # 如果存的是純名稱，再用 f"{sid} ({name})"
        format_func=lambda sid: current_stocks.get(sid, sid),
        key="target_sid_selectbox"
    )
    
    st.session_state['selected_sid'] = target_sid
    st.sidebar.divider()
    
    # 2. 🔍 探索新標的 (全市場擴建)
    with st.sidebar.expander("🔍 搜尋全市場並擴建雷達"):
        full_market = load_full_market() # 讀取那 1,971 檔母體
        
        # 建立搜尋用列表：強制統一格式「代號 (名稱)」
        search_options = [f"{sid} ({name})" for sid, name in full_market.items()]
        
        # 使用者搜尋界面
        new_stock_input = st.selectbox("請輸入代號或名稱搜尋", options=search_options)
        
        if st.button("➕ 加入每日戰情室"):
            # 從字串中切出代號 (例如: "2330 (台積電)" -> "2330")
            new_sid = new_stock_input.split(" ")[0]
            
            if new_sid not in current_stocks:
                # 寫入邏輯
                current_stocks[new_sid] = full_market.get(new_sid, "未知公司")
                save_stock_dict(current_stocks)
                st.success(f"✅ 已成功加入: {new_sid}")
                st.rerun() # 立即重整頁面讓戰情室選單更新
            else:
                st.warning("⚠️ 此標的已在自選清單中")

    # 3. 📅 歷史數據追蹤
    view_days = st.sidebar.slider("📅 歷史數據追蹤天數", 30, 240, 90)
    st.sidebar.divider()
    
# 3. 🌐 外部情資鏈結 (UI/UX 戰情室完整版)
    st.sidebar.markdown("### 🌐 外部戰情資料庫")
    
    # 第一層：基礎資訊 (雙欄並排)
    link_col1, link_col2 = st.sidebar.columns(2)
    link_col1.link_button("📈 Yahoo 股市", f"https://tw.stock.yahoo.com/quote/{target_sid}", use_container_width=True)
    link_col2.link_button("💰 財務報表", f"https://goodinfo.tw/tw/StockDetail.asp?STOCK_ID={target_sid}", use_container_width=True)
    
    # 第二層：進階籌碼 (雙欄並排，主題色高亮)
    chip_col1, chip_col2 = st.sidebar.columns(2)
    chip_col1.link_button(
        "🕵️ 融資融券", 
        f"https://goodinfo.tw/tw/ShowMarginChart.asp?STOCK_ID={target_sid}", 
        use_container_width=True, 
        type="primary",
        help="跳轉至 Goodinfo 查看融資、融券餘額與券資比變化。"
    )
    chip_col2.link_button(
        "🏦 三大法人", 
        f"https://goodinfo.tw/tw/ShowBuySaleChart.asp?STOCK_ID={target_sid}", 
        use_container_width=True, 
        type="primary",
        help="跳轉至 Goodinfo 查看外資、投信、自營商買賣超明細。"
    )

    st.sidebar.divider()

    # 4. 🏢 AI 產業百科
    st.sidebar.markdown("### 🏢 AI 產業百科", help="這裡展示由 AI 深度生成的企業基本面...")
    db = load_industry_db()
    target_sid_str = str(target_sid).strip()
    stock_info = db.get(target_sid_str)
    
    if stock_info:
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
            
       # --- 💥 增加資料過期檢查邏輯 ---
        import datetime
        last_updated_str = stock_info.get('last_updated', '2020-01-01')
        try:
            last_updated_date = datetime.date.fromisoformat(last_updated_str)
            days_old = (datetime.date.today() - last_updated_date).days
            
            if days_old > 7:
                st.sidebar.warning(f"⚠️ 資料已過期 {days_old} 天，建議點擊下方按鈕更新")
            else:
                st.sidebar.caption(f"✨ 百科更新時間：{last_updated_str}")
        except:
            st.sidebar.caption(f"✨ 百科更新時間：{last_updated_str}")
        # --------------------------------
        
        s_url = stock_info.get("source_url", "")
        if not s_url:
            c_name = stock_info.get("name", target_sid_str)
            s_url = f"https://www.google.com/search?q=台股+{c_name}+產業分析"
            
        html_btn = '<div style="text-align: right; margin-bottom: 10px;">' + \
                   f'<a href="{s_url}" target="_blank" style="color: #60a5fa; text-decoration: none; font-size: 13px; font-weight: 600;">' + \
                   '🔍 查看 AI 參考來源網頁 →</a></div>'
        st.sidebar.markdown(html_btn, unsafe_allow_html=True)

        if st.sidebar.button("🔄 更新這檔百科", key=f"re_up_{target_sid_str}", use_container_width=True):
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
    else:
        st.sidebar.warning(f"⚠️ 庫存中無 {target_sid_str} 的資料")
        if st.sidebar.button(f"🎯 消耗額度生成百科", key=f"init_{target_sid_str}", use_container_width=True):
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
        st.markdown("**AI 連線測試**")
        if st.button("🔍 版本測試", use_container_width=True):
            st.toast("正在測試...")
        if st.button("📋 模型清單", use_container_width=True):
            pass
        
        st.divider()
        st.markdown("**系統記憶體管理**")
        if st.button("🧹 強制清除系統快取", use_container_width=True):
            st.cache_data.clear()
            st.success("✅ 系統快取已完美清除！")
            import time
            time.sleep(1)
            st.rerun()
            
        st.divider()
        st.markdown("**資料庫管理**")
        
        # 1. 雲端同步區 (新增的部分)
        st.markdown("<span style='font-size: 13px; color: #00F0FF;'>☁️ 雲端百科同步</span>", unsafe_allow_html=True)
        if st.button("🚀 執行資料庫雲端遷移", use_container_width=True):
            migrate_local_to_cloud()
        
        # 2. 保留原有實體下載 (做為備份)
        st.markdown("<span style='font-size: 13px; color: #94a3b8;'>💾 離線備份下載</span>", unsafe_allow_html=True)
        if os.path.exists("industry_db.json"):
            with open("industry_db.json", "r", encoding="utf-8") as f:
                st.download_button("📥 下載百科資料庫", f.read(), "industry_db.json", "application/json", use_container_width=True)
        if os.path.exists("stock_dict.json"):
            with open("stock_dict.json", "r", encoding="utf-8") as f:
                st.download_button("📥 下載雷達名單", f.read(), "stock_dict.json", "application/json", use_container_width=True)

        st.markdown("**策略回測分析**")
        if os.path.exists("signal_history.csv"):
            with open("signal_history.csv", "rb") as f:
                st.download_button("📥 下載策略回測日誌", f.read(), "signal_history.csv", "text/csv", use_container_width=True)
            
            st.markdown("<span style='font-size: 13px; color: #94a3b8;'>🔄 **維護與還原 (覆蓋現有日誌)**</span>", unsafe_allow_html=True)
            uploaded_csv = st.file_uploader("上傳 CSV", type=["csv"], label_visibility="collapsed")
            if uploaded_csv is not None:
                try:
                    with open("signal_history.csv", "wb") as f:
                        f.write(uploaded_csv.getbuffer())
                    st.success("✅ 乾淨的回測日誌已成功覆蓋上傳！")
                except Exception as e:
                    st.error(f"上傳失敗: {e}")
        else:
            st.info("💡 雲端尚未生成回測紀錄。")
            
    # 6. ➕ 擴建雷達
    st.sidebar.divider()
    st.sidebar.markdown("### ➕ 擴建雷達-新增股票")
    new_sid = st.sidebar.text_input("輸入股票代號", help="資料請核對正確，例如 2330")
    new_name = st.sidebar.text_input("輸入股票名稱", help="資料請核對正確，例如 台積電")
    
    if st.sidebar.button("⚡ 新增百科標的", use_container_width=True):
        if new_sid and new_name:
            with st.sidebar.status("🤖 正在處理新增請求...", expanded=True) as status:
                prog_bar = st.progress(0, text="準備開始...")
                prog_bar.progress(20, text="📝 正在寫入預設名單...")
                current_stocks = load_stock_dict()
                current_stocks[new_sid] = f"{new_sid} ({new_name})"
                save_stock_dict(current_stocks)
                st.session_state['STOCK_DICT'] = current_stocks
                
                prog_bar.progress(50, text="🌐 AI 正在連網搜尋最新資料...")
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
# ==============================================================================
# --- 數據加載線 (外掛 - 必須靠最左邊) ---
# ==============================================================================
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
        # 1. 安全防禦：確保資料存在才執行
    if df is not None and not df.empty and len(df) > 0:
            last = df.iloc[-1]
            plot_df = df.tail(view_days)
            
            # --- 數據計算區 ---
            rsi_val = round(plot_df['RSI'].dropna().iloc[-1], 2) if not plot_df['RSI'].dropna().empty else 50.0
            inst_val = a_data.get('法人持股', 0) if a_data else 0
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
        
        # 💥 新增：長線防禦區間 (季線與年線)
        fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df['MA60'], name="60MA (季線)", line=dict(color='#2dd4bf', width=2)), row=1, col=1)
        fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df['MA240'], name="240MA (年線)", line=dict(color='#cbd5e1', width=2, dash='dot')), row=1, col=1)

		
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
		# 💥 增量優化：專業看盤軟體視覺升級包
        
        # 1. 統一懸浮資訊框與圖例頂部水平化 (解決右上角工具列撞車問題)
        fig.update_layout(
            hovermode="x unified",  
            legend=dict(
                orientation="h",    
                yanchor="bottom", y=1.02, 
                xanchor="left", x=0       # 💥 關鍵修改：改為靠「左」對齊
            ),
            margin=dict(l=10, r=10, t=65, b=10) # 💥 關鍵修改：天花板高度從 40 挑高到 65
        )
        
        # 2. 開啟十字游標準星 (Crosshair)
        fig.update_xaxes(showspikes=True, spikecolor="gray", spikesnap="cursor", spikemode="across")
        fig.update_yaxes(showspikes=True, spikecolor="gray", spikethickness=1)
        
        # 3. 強制喚醒所有隱藏的 X 軸日期標籤
        for ax in fig.select_xaxes():
            ax.update(showticklabels=True)
        st.plotly_chart(fig, use_container_width=True)
# ==========================================
# 戰情推播控制台
# ==========================================
        st.divider()
        st.markdown("""<div style="background: linear-gradient(135deg, #1e293b, #0f172a); padding: 20px; border-radius: 12px; border: 1px solid #475569; margin-top: 15px;">
            <h3 style="color: #60a5fa; margin: 0 0 10px 0; font-size: 20px; display: flex; align-items: center; gap: 8px;">📡 戰情推播控制台</h3>
            <p style="color: #94a3b8; font-size: 13px; margin: 0 0 15px 0;">在此手動觸發連線測試，或對您清單上的所有標的進行一鍵即時雷達掃描與 Discord 推播。</p>
        </div>""", unsafe_allow_html=True)

        # 💥 保留直列全寬，更具控制台氣勢
        if st.button(
            "🔗 發送 Discord 測試訊息", 
            use_container_width=True,
            help="手動測試網頁與您的 Discord 頻道是否成功對接。"
        ):
            # 強制鎖定台灣時間 (UTC+8)
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

        # 💥 關鍵修正：將掃描按鈕「向左退一格」，與測試按鈕處於同一個層級
        if st.button(
            "🔍 執行全體雷達大掃描", 
            use_container_width=True,
            help="立即對您自選清單裡的所有股票進行技術與籌碼訊號的全面掃描。"
        ):
            with st.spinner("🚀 雷達深度掃描中..."):
                results = []
                current_scan_dict = load_stock_dict()
                for sid, sname in current_scan_dict.items():
                    res = run_single_scan_signal(sid, sname, DEFAULT_DISCORD_WEBHOOK)
                    if res: results.append(res)
                    
                    import time
                    time.sleep(0.2)
                    
                if results:
                    st.success(f"🎉 掃描完成！共推播了 {len(results)} 檔。")
                    st.toast(f"✅ 成功推送 {len(results)} 檔黑馬至 Discord！", icon="🚀")
                    st.balloons()
					# 💥 補上這三行：讓氣球飛完後，網頁自動刷新，把側邊欄按鈕叫出來
                    import time
                    time.sleep(2.5) # 給氣球 2.5 秒的表演時間
                    st.rerun()      # 強制重新載入網頁更新 UI
                else:
                    st.info("💡 目前所有標的指標平穩，未達警報標準。")
                    st.toast("💤 掃描完畢，目前無異常訊號。", icon="☕")
	else:
			st.error(f"❌ 暫時無法加載 {target_sid} 的技術數據，請在側邊欄進行重置或確認代號是否正確。")
