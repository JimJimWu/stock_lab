# ==============================================================================
# 秉諺的黑馬雷達 V44.0 - 網頁儀表板主程式 
# ==============================================================================
import os
import re
import json
import time
import datetime
import requests
import pandas as pd
import yfinance as yf
import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import google.generativeai as genai
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from streamlit_autorefresh import st_autorefresh
import numpy as np

# --- 1. 頂部頁面設定與防禦 ---
st.set_page_config(layout="wide", page_title="秉諺的黑馬雷達 V44.0")

# --- 背景自動刷新設定 ---
# 每 300,000 毫秒 (即 5 分鐘) 自動觸發一次 st.rerun()
# 這會強迫網頁重新抓取最新的 Yahoo 股市數據與籌碼，但不會觸發 AI
count = st_autorefresh(interval=300000, key="f5_refresh")

# 安全讀取邏輯：優先讀取 Secrets，若無則報錯
GEMINI_API_KEY = st.secrets.get("GEMINI_API_KEY") or os.environ.get("GEMINI_API_KEY")

if not GEMINI_API_KEY:
    st.error("❌ 偵測不到 API 金鑰！請至 Streamlit Cloud Secrets 設定 'GEMINI_API_KEY'")
    st.stop()
else:
    genai.configure(api_key=GEMINI_API_KEY)

# ==============================================================================
# ☁️ 【V43.0 終極永久雲端資料庫引擎】：自選股 (watchlist) + 產業百科 (industry_db) 雙軌自動上雲
# ==============================================================================
WATCHLIST_CLOUD_KEY = "__WATCHLIST_DATA__"
DICT_FILE = "watchlist.json"
INDUSTRY_DB_FILE = "industry_db.json"
DEFAULT_DISCORD_WEBHOOK = os.environ.get("DISCORD_WEBHOOK") or ""

# --- 2. 全域時間與看盤時段判定 ---
now = datetime.datetime.now()
is_weekday = now.weekday() < 5
is_trading_hours = datetime.time(9, 0) <= now.time() <= datetime.time(13, 35)

DEFAULT_STOCKS = {
    # === 半導體與先進封測 (核心戰略區) ===
    "2330": "台積電",
    "2454": "聯發科",  
    "8299": "群聯",    
    "6147": "頎邦",    
    "3711": "日月光投控",
    "2449": "京元電子",
    "6770": "力積電",
    "6510": "精測",
    "6849": "奇鼎",
    "5297": "廣化",
    "7853": "政美應用",
    "3595": "山太士",
    
    # === AI 伺服器、散熱與電源 (大型權值區) ===
    "2317": "鴻海",    
    "2382": "廣達",
    "3231": "緯創",
    "2376": "技嘉",
    "2308": "台達電",  
    "3017": "奇鋐",
    "3324": "雙鴻",
    "2377": "微星",    
    
    # === 網通、CPO 與 光通訊 (強勢題材區) ===
    "2345": "智邦",
    "3450": "聯鈞",
    "3363": "上詮",
    "6442": "光聖",
    "6451": "訊芯-KY",
    "3163": "波若威",
    "4979": "華星光",
    "3081": "聯亞",
    "2455": "全新",
    
    # === 高階 PCB、零組件與 AI 機器人 ===
    "3533": "嘉澤",
    "2059": "川湖",
    "2359": "所羅門",
    "2327": "國巨",    
    "3037": "欣興",
    "4958": "臻鼎-KY",
    "3715": "定穎投控", 
    "1815": "富喬",
    "2486": "一銓",
    "6282": "康舒",
    
    # === 機電與綠能 (政策循環新板塊) ===
    "1504": "東元",
    "6477": "安集",

    # === 航太國防與智慧軍工 (戰略自主區) ===
    "2634": "漢翔",    
    
    # === 面板、傳產與原物料 (轉機防禦區) ===
    "2002": "中鋼",    
    "2408": "南亞科",
    "2409": "友達",    
    "3714": "富采",
    "1303": "南亞",    
    "2105": "正新",    
    "1802": "台玻",
    "9921": "巨大"     
}

def get_google_sheet():
    """建立 Google Sheets 連線"""
    creds_dict = json.loads(st.secrets["GSPREAD_JSON"])
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(creds)
    return client.open_by_url(st.secrets["SHEET_URL"]).sheet1

def sync_all_to_cloud(industry_db_dict, watchlist_dict=None):
    """將產業百科與自選股名單一併安全寫入 Google Sheets 與本地暫存檔"""
    try:
        clean_db = {str(k): v for k, v in industry_db_dict.items() if str(k) != WATCHLIST_CLOUD_KEY}
        with open(INDUSTRY_DB_FILE, "w", encoding="utf-8") as f:
            json.dump(clean_db, f, ensure_ascii=False, indent=4)
        
        if watchlist_dict is not None:
            pure_wl = {str(k): v for k, v in watchlist_dict.items() if "(⚡雷達)" not in str(v)}
            with open(DICT_FILE, "w", encoding="utf-8") as f:
                json.dump(pure_wl, f, ensure_ascii=False, indent=4)
        else:
            if os.path.exists(DICT_FILE):
                with open(DICT_FILE, "r", encoding="utf-8") as f:
                    pure_wl = json.load(f)
            else:
                pure_wl = DEFAULT_STOCKS.copy()

        sheet = get_google_sheet()
        rows = [[WATCHLIST_CLOUD_KEY, json.dumps(pure_wl, ensure_ascii=False)]]
        for sid, data in clean_db.items():
            rows.append([str(sid), json.dumps(data, ensure_ascii=False)])
        
        sheet.clear()
        sheet.append_row(["sid", "data"])
        sheet.append_rows(rows)
        return True
    except Exception as e:
        print(f"雲端同步寫入失敗: {e}")
        return False

def load_cloud_master_data():
    """一次性從 Google Sheets 讀取【自選股名單】與【產業百科】，並與本地檔案智慧取聯集合併"""
    cloud_wl = {}
    cloud_db = {}
    try:
        sheet = get_google_sheet()
        records = sheet.get_all_records()
        for row in records:
            sid_key = str(row.get('sid', '')).strip()
            raw_json = row.get('data', '')
            if not sid_key or not raw_json:
                continue
            if sid_key == WATCHLIST_CLOUD_KEY:
                cloud_wl = json.loads(raw_json)
            else:
                cloud_db[sid_key] = json.loads(raw_json)
    except Exception as e:
        print(f"讀取雲端試算表失敗，改用本地備份: {e}")

    local_db = {}
    if os.path.exists(INDUSTRY_DB_FILE):
        try:
            with open(INDUSTRY_DB_FILE, "r", encoding="utf-8") as f:
                local_db = json.load(f)
        except Exception:
            pass
    merged_db = {**local_db, **cloud_db}

    try:
        with open(INDUSTRY_DB_FILE, "w", encoding="utf-8") as f:
            json.dump(merged_db, f, ensure_ascii=False, indent=4)
    except Exception:
        pass

    return cloud_wl, merged_db

def load_industry_db():
    _, merged_db = load_cloud_master_data()
    return merged_db

def migrate_local_to_cloud():
    """雙向智慧合併同步：將本地與雲端資料取聯集後寫回 Google Sheets，絕不誤刪新資料！"""
    _, merged_db = load_cloud_master_data()
    current_wl = st.session_state.get('STOCK_DICT', load_stock_dict())
    if sync_all_to_cloud(merged_db, current_wl):
        st.success(f"✅ 雙向智慧同步完成！雲端已永久保存 {len(current_wl)} 檔自選股與 {len(merged_db)} 筆 AI 百科！")
    else:
        st.error("❌ 雲端同步失敗，請檢查 Secrets 設定。")
def calculate_structural_support(data_df):
            try:
                if data_df is None or data_df.empty or len(data_df) < 20:
                    fb = float(data_df['Close'].iloc[-1]) * 0.95 if data_df is not None and not data_df.empty else 0.0
                    return round(fb, 2), "基礎價格支撐"

                c_df = data_df.copy()
                cur_c = float(c_df['Close'].iloc[-1])

                # 留倉資金時間成本：20MA (月線) 與 60MA (季線) 純收盤價
                m20 = float(c_df['Close'].tail(20).mean())
                m60 = float(c_df['Close'].tail(60).mean()) if len(c_df) >= 60 else m20

                # 計算 14 日 ATR (真實波幅) 過濾盤中當沖洗盤雜訊
                c_df['Prev_Close'] = c_df['Close'].shift(1)
                c_df['TR1'] = c_df['High'] - c_df['Low']
                c_df['TR2'] = (c_df['High'] - c_df['Prev_Close']).abs()
                c_df['TR3'] = (c_df['Low'] - c_df['Prev_Close']).abs()
                c_df['TR'] = c_df[['TR1', 'TR2', 'TR3']].max(axis=1)
                atr_val = float(c_df['TR'].tail(14).mean())

                # 波段 ATR 吊燈防線 (近 20 日最高收盤價回推 2.5 倍 ATR)
                high_20 = float(c_df['Close'].tail(20).max())
                atr_sup = high_20 - (2.5 * atr_val)

                if cur_c >= m60 * 1.10:
                    sup_price = max(m60, (m20 * 0.5 + atr_sup * 0.5))
                    desc = f"波段多頭結構｜結合 20MA留倉線 ({round(m20, 1)}元) 與 ATR波動底線 ({round(atr_sup, 1)}元)"
                else:
                    sup_price = m60
                    desc = f"中長線價值中樞｜以 60MA季線實質留倉成本 ({round(m60, 1)}元) 為關鍵多空分水嶺"

                return round(float(sup_price), 2), desc
            except Exception:
                fb = float(data_df['Close'].iloc[-1]) * 0.95 if data_df is not None and not data_df.empty else 0.0
                return round(fb, 2), "系統預設支撐"
# ==============================================================================
# 🧬 【K 線型態雙胞胎檢索引擎 (Time-Series Similarity Search)】
# ==============================================================================
def find_kline_twins(target_sid, candidate_tickers, window=20, lag_days=0, top_n=5):
    """
    透過 Z-Score 標準化與皮爾森相關係數，尋找全市場型態高度相似的潛力股。
    """
    try:
        all_symbols = list(set([target_sid] + candidate_tickers))
        raw_data = yf.download(all_symbols, period="3mo", group_by="column", progress=False, threads=True)
        
        if raw_data.empty or 'Close' not in raw_data:
            return []

        close_df = raw_data['Close'].dropna(how='all', axis=1)
        vol_df = raw_data['Volume'].dropna(how='all', axis=1)

        if target_sid not in close_df.columns or len(close_df) < (window + lag_days):
            return []

        if lag_days > 0:
            target_series = close_df[target_sid].iloc[-(window + lag_days) : -lag_days]
        else:
            target_series = close_df[target_sid].iloc[-window:]

        t_std = target_series.std()
        if t_std == 0 or np.isnan(t_std):
            return []
        target_norm = (target_series.values - target_series.mean()) / t_std

        recent_closes = close_df.iloc[-window:]
        recent_vols = vol_df.iloc[-5:].mean() / 1000.0  
        ma60_series = close_df.iloc[-60:].mean()        

        results = []
        for sym in recent_closes.columns:
            if sym == target_sid:
                continue
            
            if recent_vols.get(sym, 0) < 800:
                continue
                
            cand_series = recent_closes[sym].dropna()
            if len(cand_series) < window:
                continue

            cur_price = float(cand_series.iloc[-1])
            ma60_val = float(ma60_series.get(sym, cur_price))

            if cur_price < ma60_val:
                continue

            c_std = cand_series.std()
            if c_std == 0 or np.isnan(c_std):
                continue
            cand_norm = (cand_series.values - cand_series.mean()) / c_std
            
            corr = float(np.corrcoef(target_norm, cand_norm)[0, 1])
            
            if corr >= 0.80:
                results.append({
                    "symbol": sym,
                    "similarity": round(corr * 100, 1),
                    "price": round(cur_price, 2),
                    "vol_ma5": int(recent_vols.get(sym, 0)),
                    "ma60_buffer": round(((cur_price - ma60_val) / ma60_val) * 100, 1)
                })

        results.sort(key=lambda x: x["similarity"], reverse=True)
        return results[:top_n]
    except Exception:
        return []

# ==============================================================================
# 🤖 AI 產業百科生成引擎
# ==============================================================================
def generate_ai_insights(company_name, summary):
    """自適應驗證版：自動抓取該 API Key 真正開通的模型，絕不盲目硬塞造成 404"""
    match = re.match(r'^([A-Za-z0-9]+)(?:\s*\((.*?)\))?', company_name.strip())
    ticker = match.group(1) if match else company_name
    pure_name = match.group(2) if match and match.group(2) else company_name

    prompt = f"""
    {summary}
    [目標企業]: {pure_name} (代號: {ticker})
    [要求]: 僅輸出 JSON，若查無資料，Value 請填入「【資料不足，無法確認】」，competitors 請填 []。
    """
    source_url = f"https://www.google.com/search?q=台股+{ticker}+{pure_name}+產業分析"

    try:
        available_models = [
            m.name.replace("models/", "") 
            for m in genai.list_models() 
            if 'generateContent' in m.supported_generation_methods
        ]
    except Exception:
        available_models = ['gemini-2.5-flash']

    priorities = ['gemini-2.5-flash', 'gemini-1.5-pro', 'gemini-pro']
    run_list = [m for m in priorities if m in available_models]
    if not run_list:
        run_list = available_models[:3]

    last_err = ""
    for model_name in run_list:
        try:
            model = genai.GenerativeModel(
                model_name=model_name,
                generation_config={"response_mime_type": "application/json"}
            )
            response = model.generate_content(prompt)
            text = response.text.strip()
            text = re.sub(r'^```(?:json)?\s*|\s*```$', '', text, flags=re.IGNORECASE)
            ai_dict = json.loads(text)
            ai_dict['source_url'] = source_url
            return ai_dict
        except Exception as e:
            last_err = str(e)
            if "429" in last_err or "quota" in last_err.lower():
                continue
            break

    return {
        "company_brief": f"⚠️ 解析中斷: {last_err}", 
        "overview": "【資料不足，無法確認】", 
        "value_chain": "【資料不足，無法確認】", 
        "competitors": [], 
        "drivers": "【資料不足，無法確認】",
        "source_url": source_url
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
# 🎨 【V41.0 美式機構級暗色交易卡片渲染器】
# ==============================================================================
def custom_diagnostic_card(title, text, card_type="info"):
    theme_colors = {
        "success": {"border": "#10b981", "title_color": "#34d399"},
        "warning": {"border": "#f59e0b", "title_color": "#fbbf24"},
        "error":   {"border": "#ef4444", "title_color": "#f87171"},
        "info":    {"border": "#3b82f6", "title_color": "#60a5fa"}
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

# --- 全市場母體資料庫 ---
def load_full_market():
    for fname in ["full_market_dict.json", "stock_dict.json"]:
        if os.path.exists(fname):
            try:
                with open(fname, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                print(f"讀取 {fname} 失敗: {e}")
    return {}

# --- 永久資料庫讀寫 (V43.0 自動雲端持久化版) ---
def load_stock_dict():
    current_data = {k: f"{k} ({v})" if str(k) not in str(v) else str(v) for k, v in DEFAULT_STOCKS.items()}
    
    if os.path.exists(DICT_FILE):
        try:
            with open(DICT_FILE, "r", encoding="utf-8") as f:
                saved_data = json.load(f)
            if saved_data and isinstance(saved_data, dict):
                for k, v in saved_data.items():
                    pure_name = str(v).replace(str(k), "").replace("台股代號", "").replace("(", "").replace(")", "").strip()
                    current_data[str(k)] = f"{k} ({pure_name})"
        except Exception as e:
            print(f"讀取 {DICT_FILE} 失敗: {e}")
    
    try:
        cloud_wl, db = load_cloud_master_data()
        if cloud_wl and isinstance(cloud_wl, dict):
            for k, v in cloud_wl.items():
                pure_name = str(v).replace(str(k), "").replace("台股代號", "").replace("(", "").replace(")", "").strip()
                current_data[str(k)] = f"{k} ({pure_name})"
                
        #for sid, info in db.items():
             #sid_str = str(sid).strip()
             #if sid_str not in current_data and sid_str != WATCHLIST_CLOUD_KEY:
                 #company_name = info.get("name", "未知名稱").replace("台股代號 ", "")
                 #if sid_str in company_name:
                     #current_data[sid_str] = company_name
                 #else:
                     #current_data[sid_str] = f"{sid_str} ({company_name})"
    except Exception:
        pass
    
    if os.path.exists("radar_elite.json"):
        try:
            with open("radar_elite.json", "r", encoding="utf-8") as f:
                radar_stocks = json.load(f)
            for sid, sname in radar_stocks.items():
                if sid not in current_data:
                    pure_name = sname.replace(str(sid), "").replace("台股代號", "").replace("(", "").replace(")", "").strip()
                    current_data[sid] = f"{sid} ({pure_name}) (⚡雷達)"
        except Exception:
            pass
    
    return current_data

def save_stock_dict(data):
    """當使用者在網頁新增或移除自選股時，自動寫入本地與 Google Sheets 雲端永久保存！"""
    try:
        pure_data = {str(k): v for k, v in data.items() if "(⚡雷達)" not in str(v)}
        with open(DICT_FILE, "w", encoding="utf-8") as f:
            json.dump(pure_data, f, ensure_ascii=False, indent=4)
        
        current_db = st.session_state.get('INDUSTRY_DB', load_industry_db())
        sync_all_to_cloud(current_db, pure_data)
        return True
    except Exception as e:
        print(f"儲存 {DICT_FILE} 失敗: {e}")
        return False

# 💥 【V34.2 升級：富文本量化回測記錄器】
def log_signal_to_csv(sid, sname, price, embed):
    log_file = "signal_history.csv"
    tz_tw = datetime.timezone(datetime.timedelta(hours=8))
    now_time = datetime.datetime.now(tz_tw).strftime('%Y-%m-%d %H:%M:%S')
    file_exists = os.path.isfile(log_file)
    
    try:
        pure_sname = sname.split("(")[1].split(")")[0] if ("(" in sname and ")" in sname) else sname
        desc = embed.get("description", "").replace("*", "").replace("`", "").replace("\n", " | ")
        tech_vol = ""
        for field in embed.get("fields", []):
            if "技術" in field.get("name", ""):
                tech_vol = field.get("value", "").replace("\n", " | ").replace("`", "")
        
        with open(log_file, mode='a', encoding='utf-8-sig', newline='') as f:
            if not file_exists:
                f.write("日期時間,股票代號,股票名稱,觸發價格,核心訊號,技術與量能\n")
            clean_desc = desc.replace(',', '，')
            clean_tech = tech_vol.replace(',', '，')
            f.write(f"{now_time},{sid},{pure_sname},{price},{clean_desc},{clean_tech}\n")
    except Exception as e:
        print(f"寫入 CSV 失敗: {e}")

if 'STOCK_DICT' not in st.session_state:
    st.session_state['STOCK_DICT'] = load_stock_dict()

if 'INDUSTRY_DB' not in st.session_state:
    st.session_state['INDUSTRY_DB'] = load_industry_db()

STOCK_DICT = st.session_state['STOCK_DICT']
INDUSTRY_DB = st.session_state['INDUSTRY_DB']

# ==============================================================================
# --- 🏢 百科生成模組 (具備 429 配額超標與異常中斷防禦機制) ---
# ==============================================================================
def auto_update_industry_db(sid):
    sid = str(sid).strip()
    _, db = load_cloud_master_data()
    
    current_dict = st.session_state.get('STOCK_DICT', STOCK_DICT)
    company_name = current_dict.get(sid, f"台股代號 {sid}")
    
    prompt_context = "請提供以下台股公司的產業分析 (JSON格式: company_brief, overview, value_chain, competitors, drivers)。"
    ai_data = generate_ai_insights(company_name, prompt_context)
    
    if not ai_data or not isinstance(ai_data, dict):
        return False, "⚠️ AI 引擎無回應或未回傳有效字典資料"

    brief_text = str(ai_data.get("company_brief", "")).strip()
    overview_text = str(ai_data.get("overview", "")).strip()

    # 🛡️ 核心防禦濾網：嚴格阻絕任何報錯文字、429 配額超標與中斷訊息寫入資料庫
    has_error_pattern = (
        brief_text.startswith("⚠️") 
        or "429" in brief_text 
        or "quota" in brief_text.lower()
        or "exceeded" in brief_text.lower()
        or overview_text == "【資料不足，無法確認】" and brief_text == ""
    )

    if not has_error_pattern and len(brief_text) > 10:
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
        
        # 雙向同步至 Google Sheets 與本地 JSON
        sync_all_to_cloud(db, current_dict)
        st.session_state['INDUSTRY_DB'] = db
        return True, f"✅ {company_name} 更新並自動同步至雲端成功"
    
    # 若被濾網攔截，回傳具體的錯誤原因，絕不破壞既有資料庫
    error_msg = brief_text if brief_text else "AI 百科生成不完整，已取消寫入資料庫"
    return False, error_msg

# --- K線獲取與修正清洗防線 ---
cache_ttl = 300 if is_trading_hours else 3600

@st.cache_data(ttl=cache_ttl)
def get_stock_df(sid):
    sid = str(sid).split('(')[0].split(' ')[0].strip()
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

                # 💥 【V41.0 核心黑科技：動態跨日日 K 補齊演算法】
                try:
                    f_info = ticker.fast_info
                    if f_info:
                        today_idx = df.index[-1]
                        
                        latest_price = float(f_info['last_price']) if f_info['last_price'] else 0.0
                        latest_open = float(f_info['open']) if (f_info['open'] and f_info['open'] > 0) else latest_price
                        latest_high = float(f_info['day_high']) if (f_info['day_high'] and f_info['day_high'] > 0) else latest_price
                        latest_low = float(f_info['day_low']) if (f_info['day_low'] and f_info['day_low'] > 0) else latest_price
                        latest_vol = f_info['last_volume'] / 1000.0 if (f_info['last_volume'] and f_info['last_volume'] > 0) else 0.01

                        today_date = datetime.date.today()
                        if today_date.weekday() == 5:
                            today_date = today_date - datetime.timedelta(days=1)
                        elif today_date.weekday() == 6:
                            today_date = today_date - datetime.timedelta(days=2)
                        
                        last_k_date = df.index[-1].date()
                        
                        if last_k_date < today_date and latest_price > 0:
                            new_timestamp = pd.Timestamp(today_date).tz_localize(df.index.tz)
                            df.loc[new_timestamp] = [latest_open, latest_high, latest_low, latest_price, latest_vol]
                        else:
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

                # 📈 技術指標計算區 (MA, MACD, KD, RSI)
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
    st.sidebar.error(f"❌ 無法抓取資料: {sid}")        
    return default_df

# ==============================================================================
# 💥 【V41.0 極速優化：直接從 df 讀取最新與昨收】
# ==============================================================================
def get_yahoo_web_quote_from_df(sid, df):
    quote = {"current": 0.0, "prev_close": 0.0, "open": 0.0, "high": 0.0, "low": 0.0, "volume_txt": "0.0"}
    
    if df is not None and len(df) >= 2:
        df.index = pd.to_datetime(df.index)
        last_row = df.iloc[-1]
        today_date = last_row.name.date()
        
        quote["current"] = float(last_row['Close'])
        quote["open"] = float(last_row['Open'])
        quote["high"] = float(last_row['High'])
        quote["low"] = float(last_row['Low'])
        quote["volume_txt"] = str(round(last_row['Volume'], 1))

        historical_data = df[df.index.date < today_date]
        if not historical_data.empty:
            quote["prev_close"] = float(historical_data.iloc[-1]['Close'])
        else:
            quote["prev_close"] = float(df.iloc[-2]['Close'])
            
    return quote

# ==============================================================================
# 💥 【V42.1 黑科技：基本面數據自體運算引擎 (台積電 PE 與 OTC 財報全面修復)】
# ==============================================================================
@st.cache_data(ttl=600)
def get_analysis_data(sid):
    suffixes = [".TWO", ".TW"] if sid in ["3595", "7853", "3081"] or len(sid) == 6 else [".TW", ".TWO"]
    for suffix in suffixes:
        try:
            ticker = yf.Ticker(f"{sid}{suffix}")
            info = ticker.info or {}
            
            # --- 1. 預設從 Yahoo info 捷徑獲取 ---
            eps_val = info.get("trailingEps")
            pe_val = info.get("trailingPE")
            roe_val = info.get("returnOnEquity")
            debt_eq = info.get("debtToEquity")
            rev_growth = info.get("revenueGrowth", 0)
            inst_hold = (info.get("heldPercentInstitutions", 0) or 0) * 100

            # --- 2. 💥 動態自體補齊防線 ---
            try:
                # 抓取即時股價作為計算基準
                price = info.get("currentPrice") or info.get("previousClose")
                if not price:
                    try: price = getattr(ticker.fast_info, 'last_price', None)
                    except: pass

                # 💡【修復 A】：有 EPS 但 Yahoo 忘記給 PE (如台積電) -> 直接用即時股價反算！
                if eps_val is not None and eps_val > 0 and (pe_val is None or pd.isna(pe_val)) and price:
                    pe_val = price / eps_val

                # 💡【修復 B】：連 EPS 或 ROE 都缺 (常見於 OTC 股) -> 調閱季報重算
                if eps_val is None or roe_val is None:
                    q_inc = ticker.quarterly_income_stmt
                    q_bal = ticker.quarterly_balance_sheet
                    
                    if q_inc is not None and not q_inc.empty and 'Net Income' in q_inc.index:
                        ttm_net = q_inc.loc['Net Income'].dropna().iloc[:4].sum()
                        
                        shares = info.get("sharesOutstanding")
                        if not shares:
                            try: shares = getattr(ticker.fast_info, 'shares', None)
                            except: pass
                        
                        if shares and shares > 0:
                            calc_eps = ttm_net / shares
                            if eps_val is None: eps_val = calc_eps
                            if (pe_val is None or pd.isna(pe_val)) and price and calc_eps > 0: 
                                pe_val = price / calc_eps
                                
                        if q_bal is not None and not q_bal.empty and 'Stockholders Equity' in q_bal.index:
                            eq_series = q_bal.loc['Stockholders Equity'].dropna()
                            if not eq_series.empty:
                                equity = eq_series.iloc[0]
                                if equity > 0:
                                    if roe_val is None: roe_val = ttm_net / equity
                                    if debt_eq is None and 'Total Debt' in q_bal.index:
                                        debt_series = q_bal.loc['Total Debt'].dropna()
                                        if not debt_series.empty:
                                            debt_eq = (debt_series.iloc[0] / equity) * 100
            except Exception:
                pass 

            # --- 3. 統一格式化回傳 ---
            if info or pd.notna(eps_val):
                return {
                    "EPS": round(eps_val, 2) if pd.notna(eps_val) else "N/A",
                    "營收成長率": rev_growth if pd.notna(rev_growth) else 0,
                    "負債比": round(debt_eq, 2) if pd.notna(debt_eq) else 0,
                    "ROE": f"{round(roe_val * 100, 2)}%" if pd.notna(roe_val) else "N/A",
                    "本益比": round(pe_val, 2) if pd.notna(pe_val) else "N/A",
                    "法人持股": round(inst_hold, 2) if pd.notna(inst_hold) else 0.0
                }
        except Exception:
            continue
    return None

# ==============================================================================
# 📈 跨年度毛利與金融特許解析引擎
# ==============================================================================
@st.cache_data(ttl=3600)
def get_financial_margin_trend(sid):
    sid = str(sid).split('(')[0].split(' ')[0].strip()
    if ".TW" in sid.upper() or ".TWO" in sid.upper():
        candidate_tickers = [sid]
    else:
        suffixes = [".TWO", ".TW"] if sid in ["3595", "7853", "3081"] or len(sid) == 6 else [".TW", ".TWO"]
        candidate_tickers = [f"{sid}{s}" for s in suffixes]

    pure_num = sid.split('.')[0]
    is_finance_sector = pure_num.startswith("28") or pure_num.startswith("58")

    result = {
        "has_data": False,
        "latest_gm": "N/A",
        "latest_opm": "N/A",
        "annual_gm_dict": {},
        "quarterly_gm_dict": {},
        "gm_3y_diff": 0.0,
        "annual_rev_cagr": 0.0,
        "is_long_term_growth": False,
        "is_q_dip_opportunity": False,
        "status_tag": "⚖️ 財報中性",
        "diagnosis_text": "【資料不足，無法確認】"
    }

    if is_finance_sector:
        result["has_data"] = True
        result["latest_gm"] = "不適用(金融業)"
        result["is_long_term_growth"] = True
        result["status_tag"] = "🏛️ 金融特許・獲利穩健"
        result["diagnosis_text"] = "金融金控股無營業毛利項目，系統以整體獲利能力與籌碼鎖碼深度為主要評判防線。"
        return result

    for tk_symbol in candidate_tickers:
        try:
            ticker = yf.Ticker(tk_symbol)
            info = ticker.info or {}
            if info.get("grossMargins"):
                result["latest_gm"] = round(float(info["grossMargins"]) * 100, 2)
            if info.get("operatingMargins"):
                result["latest_opm"] = round(float(info["operatingMargins"]) * 100, 2)

            ann_stmt = ticker.income_stmt
            if ann_stmt is not None and not ann_stmt.empty:
                if "Gross Profit" in ann_stmt.index and "Total Revenue" in ann_stmt.index:
                    ann_cols = sorted(ann_stmt.columns)
                    ann_gms = {}
                    ann_revs = {}
                    for col in ann_cols:
                        yr_str = str(col.year)
                        gp = ann_stmt.loc["Gross Profit", col]
                        rev = ann_stmt.loc["Total Revenue", col]
                        if pd.notna(gp) and pd.notna(rev) and float(rev) > 0:
                            ann_gms[yr_str] = round((float(gp) / float(rev)) * 100, 2)
                            ann_revs[yr_str] = float(rev)
                    if len(ann_gms) >= 2:
                        result["has_data"] = True
                        result["annual_gm_dict"] = ann_gms
                        yrs = list(ann_gms.keys())
                        first_gm, last_gm = ann_gms[yrs[0]], ann_gms[yrs[-1]]
                        prev_gm = ann_gms[yrs[-2]]
                        result["gm_3y_diff"] = round(last_gm - first_gm, 2)
                        first_rev, last_rev = ann_revs[yrs[0]], ann_revs[yrs[-1]]
                        if first_rev > 0:
                            result["annual_rev_cagr"] = round(((last_rev - first_rev) / first_rev) * 100, 2)
                        if (last_gm >= first_gm or last_gm >= prev_gm) and result["annual_rev_cagr"] > 0:
                            result["is_long_term_growth"] = True

            q_stmt = ticker.quarterly_income_stmt
            q_rev_yoy = info.get("revenueGrowth", 0) or 0
            if q_stmt is not None and not q_stmt.empty:
                if "Gross Profit" in q_stmt.index and "Total Revenue" in q_stmt.index:
                    q_cols = sorted(q_stmt.columns)[-4:]
                    q_gms = {}
                    for col in q_cols:
                        q_label = f"{col.year}-Q{(col.month-1)//3 + 1}"
                        gp = q_stmt.loc["Gross Profit", col]
                        rev = q_stmt.loc["Total Revenue", col]
                        if pd.notna(gp) and pd.notna(rev) and float(rev) > 0:
                            q_gms[q_label] = round((float(gp) / float(rev)) * 100, 2)
                    result["quarterly_gm_dict"] = q_gms

            if result["has_data"]:
                q_vals = list(result["quarterly_gm_dict"].values())
                is_recent_q_dip = (q_rev_yoy < 0) or (len(q_vals) >= 2 and q_vals[-1] < q_vals[-2])
                if result["is_long_term_growth"] and not is_recent_q_dip:
                    result["status_tag"] = "🚀 長線毛利與營收雙成長"
                    result["diagnosis_text"] = f"歷年毛利率變動 {result['gm_3y_diff']:+.2f}%，多年度營收成長 {result['annual_rev_cagr']:+.1f}%。長線與單季基本面同步擴張！"
                elif result["is_long_term_growth"] and is_recent_q_dip:
                    result["is_q_dip_opportunity"] = True
                    result["status_tag"] = "💎 長線成長・單季逆風黃金坑"
                    result["diagnosis_text"] = f"雖近期單季小幅回檔，但跨年度毛利率成長 {result['gm_3y_diff']:+.2f}%、年度營收趨勢正成長 ({result['annual_rev_cagr']:+.1f}%)，具備長線保護傘！"
                else:
                    result["status_tag"] = "⚠️ 長線毛利或營收趨緩"
                    result["diagnosis_text"] = f"跨年度毛利率變動 {result['gm_3y_diff']:+.2f}%，年度營收變動 {result['annual_rev_cagr']:+.1f}%。宜嚴守技術與籌碼防線。"
                break
        except Exception:
            continue
    return result

# 掛單專用
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
        except Exception:
            continue
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

# ==============================================================================
# 💥 全方位評分引擎 (兼容量能爆發與量縮惜售)
# ==============================================================================
def calculate_composite_score(net_5d, volume_ratio, is_long_term_growth=False, is_q_dip=False, signal_type=""):
    if net_5d is None: net_5d = 0
    if volume_ratio is None: volume_ratio = 1.0

    chip_score = min(max((net_5d / 3000.0) * 100, 0), 100)
    if "惜售" in signal_type or "潛龍" in signal_type or volume_ratio < 0.7:
        vol_score = min(max((0.7 - volume_ratio) / 0.7 * 100, 0), 100)
    else:
        vol_score = min(max((volume_ratio - 1.15) / (3.0 - 1.15) * 100, 0), 100)
    
    base_score = (chip_score * 0.50) + (vol_score * 0.35)
    fin_bonus = 15.0 if is_long_term_growth else (10.0 if is_q_dip else 0.0)
    return round(min(base_score + fin_bonus, 100.0), 2)

# --- 雷達單次掃描 ---
def run_single_scan_signal(sid, sname, webhook_url):
    df_scan = get_stock_df(sid)
    if df_scan.empty or len(df_scan) < 20:
        return None
    
    last, prev = df_scan.iloc[-1], df_scan.iloc[-2]
    clean_prices = get_yahoo_web_quote_from_df(sid, df_scan)
    current_price = clean_prices["current"]
    prev_price = clean_prices["prev_close"]
    
    price_change = round(current_price - prev_price, 2)
    change_pct = round((price_change / prev_price) * 100, 2) if prev_price > 0 else 0.0
    change_sign = "▲" if price_change > 0 else ("▼" if price_change < 0 else " ")
    color_hex = 15158332 if price_change >= 0 else 3066993
    
    today_volume = last['Volume']
    vol_ma5 = last['Vol_MA5']
    vol_ratio = today_volume / vol_ma5 if vol_ma5 > 0 else 1
    
    a_data = get_analysis_data(sid)
    inst_val = a_data['法人持股'] if (a_data and '法人持股' in a_data and a_data['法人持股'] != 'N/A') else 0
    chip_info = f"法人持股 {round(inst_val, 1)}% " + ("(大戶鎖碼)" if inst_val > 25 else "(散戶主導)")

    df_temp = df_scan.copy()
    df_temp['Price_Diff'] = df_temp['Close'].diff()
    df_temp['Net_Force_Vol'] = df_temp.apply(
        lambda r: r['Volume'] if r['Price_Diff'] > 0 else (-r['Volume'] if r['Price_Diff'] < 0 else 0.0), axis=1
    )
    net_5d = round(df_temp['Net_Force_Vol'].tail(5).sum(), 1)
    chip_flow_status = "⚖️ 法人溫和觀望"
    if net_5d > 500:
        chip_flow_status = f"🚀 **主力強烈鎖碼進貨 (+{net_5d}張)**"
    elif net_5d < -500:
        chip_flow_status = f"⚠️ __**主力高檔調節倒貨 ({net_5d}張)**__"

    try:
        temp_df = df_scan.tail(60).copy()
        calculated_support = round(temp_df.nlargest(3, 'Volume')['Low'].mean(), 1)
        if 0.75 * current_price <= calculated_support <= 1.02 * current_price:
            weighted_support = calculated_support
        else:
            recent_low = round(df_scan.tail(10)['Low'].min(), 1)
            weighted_support = recent_low if (0.75 * current_price <= recent_low <= 1.02 * current_price) else round(current_price * 0.95, 1)
    except Exception:
        weighted_support = round(current_price * 0.95, 1)

    support_text = f"🟢 關鍵支撐守住 ({weighted_support} 元)" if current_price >= weighted_support else f"🔴 關鍵支撐失守 ({weighted_support} 元)"
    ma_status = "🔥 強勢多頭 (5 > 10 > 20MA)" if last['MA5'] > last['MA10'] > last['MA20'] else "💤 區間整理"

    status_msg = "⚖️ 區間溫和"
    signals_triggered = False

    if vol_ratio >= 1.15:
        if "倒貨" in chip_flow_status:
            status_msg = "💀【出貨陷阱】爆量但主力高檔倒貨！"
            color_hex = 7368816
            signals_triggered = True
        else:
            status_msg = "🚨【強勢突破】量能爆發且籌碼健康！"
            color_hex = 16711680
            signals_triggered = True
    elif vol_ratio < 0.7:
        if current_price >= last['MA5'] and (last['RSI'] >= 50 or inst_val > 15):
            status_msg = "💎【大戶惜售】量縮鎖碼，籌碼穩定"
            color_hex = 3447003
            signals_triggered = True

    try:
        ma60, ma240 = last.get('MA60', 0), last.get('MA240', 0)
        vol_ma20 = df_scan['Volume'].rolling(20).mean().iloc[-1]
        
        if pd.notna(ma60) and pd.notna(ma240) and pd.notna(vol_ma20):
            is_near_ma60 = abs(current_price - ma60) / ma60 <= 0.05
            is_near_ma240 = abs(current_price - ma240) / ma240 <= 0.05
            if (is_near_ma60 or is_near_ma240) and (today_volume < vol_ma20 * 0.4) and (last['RSI'] <= 35) and ("倒貨" not in chip_flow_status):
                if vol_ma20 > 300 and last['MACD_Hist'] >= prev['MACD_Hist'] and inst_val > 1.0:
                    support_type = "年線(240MA)" if is_near_ma240 else "季線(60MA)"
                    status_msg = f"🐉【深水區潛龍】測 {support_type} (籌碼安全)！"
                    color_hex = 16766720
                    signals_triggered = True
    except Exception:
        pass

    if signals_triggered:
        fin_trend = get_financial_margin_trend(sid)
        score = calculate_composite_score(
            net_5d,
            vol_ratio,
            is_long_term_growth=fin_trend["is_long_term_growth"],
            is_q_dip=fin_trend["is_q_dip_opportunity"],
            signal_type=status_msg
        )

        ann_gm_str = " ➔ ".join([f"{k[-2:]}年:{v}%" for k, v in fin_trend["annual_gm_dict"].items()]) if fin_trend["annual_gm_dict"] else f"最新: {fin_trend['latest_gm']}%"
        q_gm_str = " ➔ ".join([f"{k[-2:]}:{v}%" for k, v in fin_trend["quarterly_gm_dict"].items()]) if fin_trend["quarterly_gm_dict"] else "暫無季序列"

        alert_description = (
            f"🔥 **綜合火力評分：{score} 分**\n\n"
            f"🔗 [點擊前往 Yahoo 股市查看 {sname}](https://tw.stock.yahoo.com/quote/{sid})\n\n"
            f"**表面型態**：**`{status_msg}`**"
        )

        tz_tw = datetime.timezone(datetime.timedelta(hours=8))
        now_time = datetime.datetime.now(tz_tw).strftime('%m/%d %H:%M')
        
        embed = {
            "title": f"🚨 黑馬雷達警戒：{sname} ({sid})",
            "description": alert_description,
            "color": color_hex,
            "fields": [
                {"name": "💰 實時報價", "value": f"現價：**`{round(current_price, 2)}`** 元\n漲跌：**`{change_sign} {abs(price_change)}`** ({change_pct}%)", "inline": True},
                {"name": "📊 技術與成交量能", "value": f"RSI 指標：`{round(last['RSI'], 2)}`\n成交量比：`{round(vol_ratio, 2)}x` (`{round(today_volume, 1)}`張/`{round(vol_ma5, 1)}`張)", "inline": True},
                {"name": "🛡️ 莊家大戶防守成本線", "value": f"`{support_text}`", "inline": False},
                {"name": "📈 趨勢與內部籌碼真相", "value": f"技術趨勢：`{ma_status}`\n資金流向：{chip_flow_status}", "inline": False},
                {"name": "👥 法人籌碼動態", "value": f"`{chip_info}`", "inline": False},
                {"name": "📈 歷年毛利軌跡", "value": f"判定：**`{fin_trend['status_tag']}`**\n年度：`{ann_gm_str}`\n近季：`{q_gm_str}`\n解析：{fin_trend['diagnosis_text']}", "inline": False}
            ],
            "footer": {"text": f"秉諺的黑馬自動監控引擎 • 偵測時間: {now_time}"}
        }
        return {
            "sid": sid,
            "sname": sname,
            "score": score,
            "current_price": current_price,
            "status_msg": status_msg,
            "embed": embed
        }
    return None

# --- 全域預設選中代號 ---
current_stocks_dict = st.session_state.get('STOCK_DICT', load_stock_dict())
if 'selected_sid' not in st.session_state:
    st.session_state['selected_sid'] = list(current_stocks_dict.keys())[0] if current_stocks_dict else "2330"

# ==============================================================================
# 📊 獨立擴充模組：策略多週期持股勝率模擬分析儀 (V42.2 訊號懸停指南版)
# ==============================================================================
def render_backtest_dashboard():
    def force_clean(x):
        s = str(x)
        if "強勢突破" in s: return "🚨【強勢突破】"
        if "大戶惜售" in s: return "💎【大戶惜售】"
        if "出貨陷阱" in s: return "💀【出貨陷阱】"
        if "深水區潛龍" in s: return "🐉【深水區潛龍】"
        if "底背離" in s or "背離" in s: return "🔥【低檔底背離】"
        return "⚖️ 區間溫和"

    st.markdown("### 🏹 連續鎖碼偵測中心")
    
    col_main, col_info = st.columns([2.5, 1])
    
    with col_info:
        st.markdown("""
        <div style="background: linear-gradient(145deg, #1e293b, #0f172a); 
                    border: 1px solid #334155; 
                    border-left: 5px solid #38bdf8; 
                    padding: 18px 20px; 
                    border-radius: 12px; 
                    box-shadow: 0 6px 16px rgba(0, 0, 0, 0.35);">
            <div style="display: flex; align-items: center; gap: 10px; margin-bottom: 14px; border-bottom: 1px solid #334155; padding-bottom: 10px;">
                <span style="font-size: 22px;">🏹</span>
                <span style="color: #38bdf8; font-size: 18px; font-weight: 900; letter-spacing: 0.5px;">連續鎖碼偵測核心指南</span>
            </div>
            <div style="color: #e2e8f0; font-size: 15px; line-height: 1.7; display: flex; flex-direction: column; gap: 10px;">
                <div>
                    🔍 <strong style="color: #67e8f9;">運作原理：</strong>
                    調閱歷史資料庫，過濾出最近 N 個交易日<strong>連續出現相同核心訊號</strong>的極端強勢股。
                </div>
                <div>
                    🛡️ <strong style="color: #a7f3d0;">策略意義：</strong>
                    徹底消滅「單日一日遊」的假突破與騙線，確認主力大戶正在<strong>分批持續吸籌或強勢鎖碼</strong>。
                </div>
                <div>
                    ⏰ <strong style="color: #fed7aa;">實戰時機：</strong>
                    建議於<strong>每日開盤前（08:30）</strong>檢視最新名單，直接將其列為當日早盤核心重兵盯盤對象。
                </div>
            </div>
            <div style="margin-top: 14px; padding: 8px 12px; background: rgba(250, 204, 21, 0.08); border: 1px solid rgba(250, 204, 21, 0.25); border-radius: 8px; color: #facc15; font-size: 13.5px; font-weight: 600; display: flex; align-items: center; gap: 6px;">
                <span>📌</span>
                <span>單日多次掃描將自動以最後一次狀態為準</span>
            </div>
        </div>
        """, unsafe_allow_html=True)

    with col_main:
        log_file_path = "signal_history.csv"
        if os.path.exists(log_file_path):
            try:
                df_history = pd.read_csv(log_file_path, encoding="utf-8-sig", on_bad_lines='skip')
                if "日期時間" in df_history.columns and "股票代號" in df_history.columns and "核心訊號" in df_history.columns:
                    df_history['日期'] = pd.to_datetime(df_history['日期時間']).dt.date
                    df_history['核心訊號'] = df_history['核心訊號'].apply(force_clean)
                    df_daily = df_history.drop_duplicates(subset=['日期', '股票代號'], keep='last')
                    all_available_dates = sorted(df_daily['日期'].unique(), reverse=True)
                    
                    tab1, tab2 = st.tabs(["🚀 最新盤前偵測", "⏪ 歷史時光機回測"])
                    with tab1:
                        target_days = st.slider("🔥 選擇最近連續上榜天數", min_value=2, max_value=5, value=2, key="slider_latest")
                        consecutive_stocks = []
                        date_range_info = ""
                        if len(all_available_dates) >= target_days:
                            check_dates = all_available_dates[:target_days]
                            start_date_str = min(check_dates).strftime("%m/%d")
                            end_date_str = max(check_dates).strftime("%m/%d")
                            date_range_info = f"(觸發區間: {start_date_str} ~ {end_date_str})"
                            df_recent = df_daily[df_daily['日期'].isin(check_dates)]
                            for ticker, group in df_recent.groupby('股票代號'):
                                if len(group) == target_days and group['核心訊號'].nunique() == 1:
                                    signal_name = group['核心訊號'].iloc[0]
                                    stock_name = group['股票名稱'].iloc[0] if '股票名稱' in group.columns else ""
                                    consecutive_stocks.append(f"{ticker} {stock_name} - {signal_name}")
                        with st.expander(f"查看最近 {target_days} 日連續上榜清單 {date_range_info}", expanded=True):
                            if consecutive_stocks:
                                for item in consecutive_stocks:
                                    st.success(f"✅ {item}")
                            else:
                                st.info("該區間內，暫無連續出現相同訊號的標的。")

                    with tab2:
                        col_d1, col_d2 = st.columns(2)
                        with col_d1:
                            default_date = all_available_dates[0] if all_available_dates else datetime.date.today()
                            base_date = st.date_input("📅 選擇歷史基準日", value=default_date)
                        with col_d2:
                            target_days_hist = st.slider("🔥 選擇歷史連續天數", min_value=2, max_value=5, value=2, key="slider_hist")
                        consecutive_stocks_hist = []
                        date_range_info_hist = ""
                        past_dates = [d for d in all_available_dates if d <= base_date]
                        if len(past_dates) >= target_days_hist:
                            check_dates_hist = past_dates[:target_days_hist]
                            start_date_str_h = min(check_dates_hist).strftime("%m/%d")
                            end_date_str_h = max(check_dates_hist).strftime("%m/%d")
                            date_range_info_hist = f"(觸發區間: {start_date_str_h} ~ {end_date_str_h})"
                            df_hist_range = df_daily[df_daily['日期'].isin(check_dates_hist)]
                            for ticker, group in df_hist_range.groupby('股票代號'):
                                if len(group) == target_days_hist and group['核心訊號'].nunique() == 1:
                                    signal_name = group['核心訊號'].iloc[0]
                                    stock_name = group['股票名稱'].iloc[0] if '股票名稱' in group.columns else ""
                                    consecutive_stocks_hist.append(f"{ticker} {stock_name} - {signal_name}")
                        with st.expander(f"查看歷史 {target_days_hist} 日連續上榜清單 {date_range_info_hist}", expanded=True):
                            if consecutive_stocks_hist:
                                for item in consecutive_stocks_hist:
                                    st.success(f"✅ {item}")
                            else:
                                st.info(f"在 {date_range_info_hist} 區間內，無連續出現相同訊號的標的。")
            except Exception as e:
                st.error(f"連續偵測運算發生錯誤: {e}")
        else:
            st.warning("尚未產生回測日誌，無法進行連續偵測。")

    st.markdown("---")
    st.markdown("## 📈 策略多週期持股勝率模擬分析儀")
    
    file_path = "signal_history_backtest.csv"
    if not os.path.exists(file_path):
        st.warning(f"尚未偵測到 {file_path}，請確認回測引擎是否已執行完畢。")
        return 
    
    try:
        df = pd.read_csv(file_path, encoding="utf-8-sig", on_bad_lines='skip')
        signal_col = "核心訊號" if "核心訊號" in df.columns else ("訊號" if "訊號" in df.columns else None)
        if not signal_col:
            st.error(f"找不到『核心訊號』欄位。目前欄位: {df.columns.tolist()}")
            return
        df[signal_col] = df[signal_col].apply(force_clean)

        if "日期時間" in df.columns:
            df['日期時間'] = pd.to_datetime(df['日期時間'])
        
        col1, col2 = st.columns(2)
        with col1:
            min_date = df['日期時間'].dt.date.min()
            max_date = df['日期時間'].dt.date.max()
            default_start = max(min_date, max_date - datetime.timedelta(days=30))
            selected_dates = st.date_input("🗓️ 選擇回測區間", value=[default_start, max_date], min_value=min_date, max_value=max_date)

        with col2:
            available_signals = df[signal_col].dropna().unique().tolist()
            selected_signals = st.multiselect("🎯 選擇欲分析的訊號型態", options=available_signals, default=available_signals)

        if len(selected_dates) == 2:
            start_date, end_date = selected_dates
            df = df[(df['日期時間'].dt.date >= start_date) & (df['日期時間'].dt.date <= end_date) & (df[signal_col].isin(selected_signals))]
        elif len(selected_dates) == 1:
            start_date = selected_dates[0]
            df = df[(df['日期時間'].dt.date == start_date) & (df[signal_col].isin(selected_signals))]
        
        if df.empty:
            st.warning("⚠️ 在目前的篩選條件下，沒有找到任何符合的回測數據。")
            return

        reward_cols = [c for c in df.columns if "報酬率(%)" in c]
        df_plot = df[[signal_col] + reward_cols].copy()
        
        for col in reward_cols:
            df_plot[col] = pd.to_numeric(df_plot[col].astype(str).str.replace('%', ''), errors='coerce').fillna(0)

        periods = ["T+1", "T+3", "T+5", "T+10", "T+20"]
        fig = go.Figure()
        
        signal_color_map = {
            "🚨【強勢突破】": "#c084fc",
            "💎【大戶惜售】": "#34d399",
            "💀【出貨陷阱】": "#f87171",
            "🐉【深水區潛龍】": "#fb923c",
            "🔥【低檔底背離】": "#facc15",
            "⚖️ 區間溫和": "#94a3b8"
        }

        grouped = df_plot.groupby(signal_col)
        dynamic_insights = []

        for signal_name, group_df in grouped:
            win_rates = []
            for p in periods:
                col_name = f"{p} 報酬率(%)"
                if col_name in group_df.columns:
                    valid_data = group_df[group_df[col_name] != 0.0]
                    win_rate = (len(valid_data[valid_data[col_name] > 0]) / len(valid_data)) * 100 if len(valid_data) > 0 else 0
                    win_rates.append(win_rate)
                else:
                    win_rates.append(0)
            
            if max(win_rates) > 0:
                best_period = periods[win_rates.index(max(win_rates))]
                dynamic_insights.append(f"**{signal_name}** 在 **{best_period}** 勝率最高（`{max(win_rates):.1f}%`）")

            line_color = signal_color_map.get(signal_name, "#38bdf8")
            fig.add_trace(go.Scatter(
                x=periods, y=win_rates, mode='lines+markers+text',
                name=signal_name, text=[f"{val:.1f}%" for val in win_rates],
                textposition="top center", line=dict(width=3, color=line_color),
                marker=dict(size=10)
            ))
        
        fig.update_layout(
            title="不同訊號之多週期勝率演變交叉圖", 
            xaxis_title="持有週期", 
            yaxis_title="勝率 (%)",
            yaxis=dict(range=[0, 110]), 
            hovermode="x unified",
            legend=dict(orientation="h", yanchor="top", y=-0.2, xanchor="center", x=0.5),
            margin=dict(l=20, r=20, t=60, b=120)
        )
        
        st.plotly_chart(fig, use_container_width=True)

        if dynamic_insights:
            insight_summary = " ｜ ".join(dynamic_insights[:3])
            st.success(f"🎯 **即時週期勝率指引**：{insight_summary}")

        st.markdown("""
        <div style="background: linear-gradient(135deg, #1e293b, #0f172a); 
                    border: 1px solid #334155; 
                    border-radius: 10px; 
                    padding: 14px 18px; 
                    margin-top: 15px;">
            <div style="color: #60a5fa; font-weight: 800; font-size: 15px; margin-bottom: 8px;">
                📚 雷達五大核心訊號實戰導航（將滑鼠移至 <span style="color:#facc15; font-size: 17px; cursor: help;">❓</span> 查看操盤定義）：
            </div>
            <div style="display: flex; flex-wrap: wrap; gap: 15px; font-size: 14px; color: #cbd5e1;">
                <div>
                    <strong>🚨【強勢突破】</strong>
                    <span style="cursor: help; color: #38bdf8; font-weight: bold; font-size: 16px;" 
                          title="【量比 >= 1.15 倍 且無主力倒貨】&#10;量能爆發且籌碼集中，代表主力發起短線攻勢。&#10;💡 操作建議：適合短打追價，若 T+1~T+3 勝率見頂應即時分批停利。">❓</span>
                </div>
                <div>
                    <strong>💎【大戶惜售】</strong>
                    <span style="cursor: help; color: #38bdf8; font-weight: bold; font-size: 16px;" 
                          title="【量比 < 0.7 倍 極致量縮 + 站穩 5MA + RSI >= 50】&#10;極端洗盤結束，籌碼全數鎖定在莊家手中，散戶浮額出盡。&#10;💡 操作建議：真突破機率高達 90%，適合中長線持有 (T+5~T+10) 賺取完整波段。">❓</span>
                </div>
                <div>
                    <strong>🔥【低檔底背離】</strong>
                    <span style="cursor: help; color: #38bdf8; font-weight: bold; font-size: 16px;" 
                          title="【股價創 10 日新低，但 RSI 拒絕破低且落於 < 40 超跌區】&#10;空方力道衰竭，主力大戶趁破底恐慌默默低接吸籌。&#10;💡 操作建議：屬於左側超跌反轉點，密切注意 T+3~T+5 強彈黃金獲利期！">❓</span>
                </div>
                <div>
                    <strong>🐉【深水區潛龍】</strong>
                    <span style="cursor: help; color: #38bdf8; font-weight: bold; font-size: 16px;" 
                          title="【回測 60MA 季線 / 240MA 年線 + 極致量縮 + RSI <= 35】&#10;測試長線莊家成本線且無主力倒貨，通常具備強大防禦彈力。&#10;💡 操作建議：安全低階位階，停損空間小、波段盈虧比極佳。">❓</span>
                </div>
                <div>
                    <strong>💀【出貨陷阱】</strong>
                    <span style="cursor: help; color: #38bdf8; font-weight: bold; font-size: 16px;" 
                          title="【成交量爆量 (>= 1.15倍)，但主力籌碼 5 日急劇大倒貨】&#10;高檔假拉抬真出貨，專誘多單追高的毒蘋果。&#10;💡 操作建議：嚴禁追高接刀！已有持股者應於紅棒逢高拔檔。">❓</span>
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)

    except Exception as e:
        st.error(f"儀表板渲染失敗: {e}")

# ==============================================================================
# 🌪️ 系統擴充：大盤宏觀天氣預報 (避震器)
# ==============================================================================
@st.cache_data(ttl=3600)
def get_market_weather():
    try:
        twii = yf.download("^TWII", period="2mo", progress=False)
        if twii.empty:
            return "UNKNOWN", 0, 0
            
        if isinstance(twii.columns, pd.MultiIndex):
            twii.columns = twii.columns.get_level_values(0)
            
        twii['20MA'] = twii['Close'].rolling(window=20).mean()
        
        latest_close = float(twii['Close'].iloc[-1])
        latest_20ma = float(twii['20MA'].iloc[-1])
        prev_close = float(twii['Close'].iloc[-2])
        
        daily_drop = ((latest_close - prev_close) / prev_close) * 100
        
        if daily_drop <= -2.5 or latest_close < latest_20ma:
            return "DANGER", daily_drop, latest_close
        elif latest_close > latest_20ma and daily_drop > 0:
            return "SAFE", daily_drop, latest_close
        else:
            return "WARNING", daily_drop, latest_close
    except Exception:
        return "UNKNOWN", 0, 0

# ==============================================================================
# 側邊欄與視角切換控制
# ==============================================================================
with st.sidebar:
    st.sidebar.markdown("""
        <div style="background: linear-gradient(135deg, #1e3a8a, #000000); padding: 20px; border-radius: 15px; border: 1.5px solid #3b82f6; text-align: center; box-shadow: 0 4px 15px rgba(59, 130, 246, 0.3);">
            <h1 style="color: #60a5fa; font-size: 20px; font-weight: 900; margin: 0; letter-spacing: 2px;">🚀 戰情操控中心</h1>
            <p style="color: #94a3b8; font-size: 12px; margin-top:8px; font-weight: 500;">吳秉諺 專屬 AI 投資系統 v42.1</p>
        </div>
        """, unsafe_allow_html=True)

    st.sidebar.write("") 
    st.sidebar.markdown("### 🌐 系統視角切換")
    
    if 'app_mode' not in st.session_state:
        st.session_state['app_mode'] = "🎯 個股戰情室"
        
    col1, col2 = st.sidebar.columns(2)
    if col1.button("🎯 個股戰情", use_container_width=True, type="primary" if st.session_state['app_mode'] == "🎯 個股戰情室" else "secondary"):
        st.session_state['app_mode'] = "🎯 個股戰情室"
        st.rerun()
        
    if col2.button("📊 回測中心", use_container_width=True, type="primary" if st.session_state['app_mode'] == "📊 策略回測中心" else "secondary"):
        st.session_state['app_mode'] = "📊 策略回測中心"
        st.rerun()

    app_mode = st.session_state['app_mode']
    st.sidebar.divider()

    st.sidebar.markdown("### 🌪️ 宏觀環境監控")
    status, drop_pct, close_idx = get_market_weather()
    
    if status == "DANGER":
        st.sidebar.error(f"🔴 **極端警戒 (破月線/重挫)**\n\n大盤: {close_idx:,.0f} 點 ({drop_pct:.2f}%)\n\n系統建議：流動性枯竭風險極高，暫停所有【量能爆發突破】追價策略，提高現金水位。")
    elif status == "WARNING":
        st.sidebar.warning(f"🟡 **震盪整理 (測試支撐)**\n\n大盤: {close_idx:,.0f} 點 ({drop_pct:.2f}%)\n\n系統建議：大盤動能放緩，可縮小部位，優先關注【大戶惜售】之抗跌標的。")
    elif status == "SAFE":
        st.sidebar.success(f"🟢 **多頭防護網開啟**\n\n大盤: {close_idx:,.0f} 點 (+{drop_pct:.2f}%)\n\n系統建議：月線之上安全運行，雙核心策略可正常執行。")
    else:
        st.sidebar.warning("⚠️ **大盤連線暫時異常**\n\nYahoo API 目前無回應。這不會影響您的個股雷達功能，系統將於稍後自動重試。")
        
    st.sidebar.divider()

# 💥 畫面分流魔法 (主程式攔截點)
if app_mode == "📊 策略回測中心":
    render_backtest_dashboard()
    st.stop()

# ==============================================================================
# 🎯 個股戰情室 (當切換至個股模式時，以下才會執行)
# ==============================================================================
with st.sidebar:
    # 1. 🎯 每日戰情室 (聚焦核心標的)
    st.markdown("### 🎯 每日戰情室 (已關注)")
    current_stocks = load_stock_dict()
    options_list = list(current_stocks.keys())
    
    try:
        current_idx = options_list.index(st.session_state['selected_sid'])
    except Exception:
        current_idx = 0

    target_sid = st.selectbox(
        "選擇每日觀察標的", 
        options=options_list, 
        index=current_idx,
        format_func=lambda sid: current_stocks.get(sid, sid) if str(sid) in str(current_stocks.get(sid, '')) else f"{sid} ({current_stocks.get(sid, sid)})",
        key="target_sid_selectbox"
    )
    st.session_state['selected_sid'] = target_sid

    # 💥 【新增：一鍵刪除/移除當前標的防線】
    # 💥 【修改比例為 [5, 3]，讓「🗑️ 移除」有完美顯示空間】
    clean_target_sid = str(target_sid).strip()
    col_del_1, col_del_2 = st.columns([5, 3])
    with col_del_2:
        if st.button("🗑️ 移除", key=f"del_{clean_target_sid}", help=f"從每日戰情室移除 {clean_target_sid}，並同步更新雲端資料庫"):
            if len(current_stocks) <= 1:
                st.sidebar.error("⚠️ 戰情室至少需保留 1 檔標的，無法全數刪除！")
            else:
                current_stocks.pop(clean_target_sid, None)
                save_stock_dict(current_stocks) # 💡 自動同步寫入 watchlist.json 與 Google Sheets
                
                # 更新 Session State
                st.session_state['STOCK_DICT'] = current_stocks
                st.session_state['selected_sid'] = list(current_stocks.keys())[0]
                
                st.toast(f"🗑️ 已成功將 {clean_target_sid} 移出戰情室！", icon="✅")
                time.sleep(0.5)
                st.rerun()

    st.divider()
    
    # 2. 🔍 探索新標的 (全市場擴建)
    with st.expander("🔍 搜尋全市場並擴建雷達"):
        full_market = load_full_market()
        search_options = [f"{sid} ({name})" for sid, name in full_market.items()]
        new_stock_input = st.selectbox("請輸入代號或名稱搜尋", options=search_options)
        
        if st.button("➕ 加入每日戰情室", use_container_width=True):
            if new_stock_input:
                raw_key = new_stock_input.split(" ")[0].strip()
                stock_name = full_market.get(raw_key, "未知標的")
                clean_new_sid = raw_key.split(".")[0]
                formatted_name = f"{clean_new_sid} ({stock_name})"
                
                current_stocks = load_stock_dict()
                if clean_new_sid not in current_stocks:
                    current_stocks[clean_new_sid] = formatted_name
                    save_stock_dict(current_stocks)
                    
                    st.session_state['STOCK_DICT'] = current_stocks
                    st.session_state['selected_sid'] = clean_new_sid
                    
                    st.success(f"✅ 已成功加入: {formatted_name} \n(百科請視需求手動點擊生成)")
                    time.sleep(0.8)
                    st.rerun()
                else:
                    st.warning(f"⚠️ {clean_new_sid} 此標的已在自選清單中，請勿重複新增！")
                
    # 3. 📅 歷史數據追蹤
    view_days = st.slider("📅 歷史數據追蹤天數", 30, 240, 90)
    st.divider()
    
    # 4. 🌐 外部情資鏈結
    st.markdown("### 🌐 外部戰情資料庫")
    link_col1, link_col2 = st.columns(2)
    link_col1.link_button("📈 Yahoo 股市", f"https://tw.stock.yahoo.com/quote/{target_sid}", use_container_width=True)
    link_col2.link_button("💰 財務報表", f"https://goodinfo.tw/tw/StockDetail.asp?STOCK_ID={target_sid}", use_container_width=True)
    
    chip_col1, chip_col2 = st.columns(2)
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

    st.divider()

# ==============================================================================
# 🏢 AI 產業百科（全區塊通用防禦排版引擎）
# ==============================================================================
st.sidebar.markdown("### 🏢 AI 產業百科", help="這裡展示由 AI 深度生成的企業基本面...")
db = load_industry_db()
target_sid_str = str(target_sid).strip()
stock_info = db.get(target_sid_str)

if stock_info:
    def universal_format(data):
        """全區塊通用解析器：支援遞迴解析多維度物件"""
        if not data or data == "【資料不足，無法確認】":
            return "暫無資料"
        
        lines = []
        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict):
                    name = item.get("name") or item.get("company") or item.get("title") or "相關項目"
                    desc = item.get("description") or item.get("desc") or item.get("detail") or ""
                    lines.append(f"- **{name}**：{desc}" if desc else f"- **{name}**")
                elif isinstance(item, list):
                    lines.append(universal_format(item))
                else:
                    lines.append(f"- {str(item).strip()}")
            return "\n\n".join(lines)
            
        elif isinstance(data, dict):
            for k, v in data.items():
                label = str(k).strip()
                if isinstance(v, list):
                    sub_content = "\n".join([f"  • {x}" for x in v])
                    lines.append(f"**🔸 {label}**：\n{sub_content}")
                elif isinstance(v, dict):
                    lines.append(f"**🔸 {label}**：\n{universal_format(v)}")
                else:
                    lines.append(f"**🔸 {label}**：{str(v).strip()}")
            return "\n\n".join(lines)
            
        return str(data).strip()

    # 五大百科區塊全面採用 universal_format
    with st.sidebar.expander("🎯 個股主要業務", expanded=True):
        st.info(universal_format(stock_info.get("company_brief")))
        
    with st.sidebar.expander("📍 產業市場規模", expanded=False):
        st.info(universal_format(stock_info.get("overview")))
        
    with st.sidebar.expander("🔗 產業價值鏈", expanded=False):
        st.info(universal_format(stock_info.get("value_chain")))
        
    with st.sidebar.expander("🔗 相關競爭對手", expanded=False):
        st.markdown(universal_format(stock_info.get("competitors")))
        
    with st.sidebar.expander("📈 產業驅動因子", expanded=False):
        st.info(universal_format(stock_info.get("drivers")))
            
    # ✅ 修復 1：退出 expander，與 expander 同層級對齊
    last_updated_str = stock_info.get('last_updated', '2020-01-01')
    try:
        last_updated_date = datetime.date.fromisoformat(last_updated_str)
        days_old = (datetime.date.today() - last_updated_date).days
        if days_old > 7:
            st.sidebar.warning(f"⚠️ 資料已過期 {days_old} 天，建議點擊下方按鈕更新")
        else:
            st.sidebar.caption(f"✨ 百科更新時間：{last_updated_str}")
    except Exception:
        st.sidebar.caption(f"✨ 百科更新時間：{last_updated_str}")
        
    s_url = stock_info.get("source_url") or f"https://www.google.com/search?q=台股+{stock_info.get('name', target_sid_str)}+產業分析"
    html_btn = (
        '<div style="text-align: right; margin-bottom: 10px;">'
        f'<a href="{s_url}" target="_blank" style="color: #60a5fa; text-decoration: none; font-size: 13px; font-weight: 600;">'
        '🔍 查看 AI 參考來源網頁 →</a></div>'
    )
    st.sidebar.markdown(html_btn, unsafe_allow_html=True)

    if st.sidebar.button("🔄 更新這檔百科", key=f"re_up_{target_sid_str}", use_container_width=True):
        with st.sidebar.status(f"🚀 正在重塑 {target_sid_str} 產業百科...", expanded=True) as status:
            prog_bar = st.progress(0, text="準備發動 AI 引擎...")
            prog_bar.progress(30, text="🌐 正在連網搜尋最新產業動態...")
            success, msg = auto_update_industry_db(target_sid_str)
            if success:
                prog_bar.progress(80, text="💾 正在將新資料寫入 JSON 資料庫...")
                time.sleep(0.5) 
                prog_bar.progress(100, text="✅ 百科更新成功！")
                status.update(label="✅ 百科更新成功！", state="complete", expanded=False)
                st.rerun()
            else:
                prog_bar.error("⚠️ 更新過程發生中斷")
                st.write(f"系統回報: {msg}")
                status.update(label="❌ 更新失敗", state="error")
                
else:
    # ✅ 確保 else 區塊精確縮排
    st.sidebar.warning(f"⚠️ 庫存中無 {target_sid_str} 的資料")
    if st.sidebar.button("🎯 消耗額度生成百科", key=f"init_{target_sid_str}", use_container_width=True):
        with st.sidebar.status(f"🤖 正在為 {target_sid_str} 建立全新百科...", expanded=True) as status:
            prog_bar = st.progress(0, text="準備發動 AI 引擎...")
            prog_bar.progress(30, text="🌐 AI 正在連網深度檢索...")
            success, msg = auto_update_industry_db(target_sid_str)
            if success:
                prog_bar.progress(80, text="💾 正在建檔寫入資料庫...")
                time.sleep(0.5)
                prog_bar.progress(100, text="✅ 全新百科建立完成！")
                status.update(label="🎉 百科建檔成功！", state="complete", expanded=False)
                st.rerun()
            else:
                prog_bar.error("⚠️ 生成過程發生中斷")
                st.write(f"系統回報: {msg}")
                status.update(label="❌ 生成失敗", state="error")

# ✅ 修復 2：完全退出 if/else 區塊（回到最外層），確保系統工具永遠可見且不會引發 IndentationError
# 6. 🩺 系統檢修區
st.sidebar.divider()
with st.sidebar.expander("🛠️ 系統後勤工具", expanded=False):
    st.markdown("**AI 連線測試**")
    if st.button("🔍 版本測試", use_container_width=True):
        st.toast("正在測試...")
    if st.button("📋 模型清單", use_container_width=True):
        try:
            models = [m.name.replace("models/", "") for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
            st.write("✅ 您的 API 金鑰確定開通支援的模型清單：")
            st.json(models)
        except Exception as ex:
            st.error(f"查詢失敗: {ex}")
            
    st.divider()
    st.markdown("**系統記憶體管理**")
    if st.button("🧹 強制清除系統快取", use_container_width=True):
        st.cache_data.clear()
        st.success("✅ 系統快取已完美清除！")
        time.sleep(1)
        st.rerun()
        
    st.divider()
    st.markdown("**資料庫管理 (已開啟全自動雲端同步)**")
    st.markdown("<span style='font-size: 13px; color: #00F0FF;'>☁️ 雲端雙向智慧合併</span>", unsafe_allow_html=True)
    if st.button("🚀 執行本地與雲端智慧合併", use_container_width=True, help="將本地 JSON 與 Google Sheets 取聯集智慧合併，絕不誤刪新資料！"):
        migrate_local_to_cloud()
    
    st.markdown("<span style='font-size: 13px; color: #94a3b8;'>💾 離線備份下載 (供更新 Gem 與 GitHub)</span>", unsafe_allow_html=True)
    latest_db_json = json.dumps(st.session_state.get('INDUSTRY_DB', {}), ensure_ascii=False, indent=4)
    st.download_button(
        "📥 下載最新百科 (industry_db.json)",
        latest_db_json,
        "industry_db.json",
        "application/json",
        use_container_width=True
    )
    
    clean_wl_dict = {
        k: str(v).replace(str(k), "").replace("(", "").replace(")", "").strip()
        for k, v in st.session_state.get('STOCK_DICT', {}).items()
        if "(⚡雷達)" not in str(v)
    }
    latest_wl_json = json.dumps(clean_wl_dict, ensure_ascii=False, indent=4)
    st.download_button(
        "📥 下載最新自選股 (watchlist.json)",
        latest_wl_json,
        "watchlist.json",
        "application/json",
        use_container_width=True
    )

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

# ==============================================================================
# --- 數據加載線 ---
# ==============================================================================
match = re.search(r'\d+', str(target_sid))
clean_sid = match.group() if match else str(target_sid)

df = get_stock_df(clean_sid)
a_data = get_analysis_data(clean_sid)
bid_p, ask_p, bid_s, ask_s = get_realtime_order(clean_sid)

# ==============================================================================
# 💥 【V41.0 物理對齊：極致對稱的排版層級結構】
# ==============================================================================
if df is not None and not df.empty:
    last, prev = df.iloc[-1], df.iloc[-2]
    clean_prices = get_yahoo_web_quote_from_df(clean_sid, df)
    current_price = clean_prices["current"]
    prev_price = clean_prices["prev_close"]
    
    diff = round(current_price - prev_price, 2)
    diff_pct = round((diff / prev_price) * 100, 2) if prev_price > 0 else 0
    price_color = "#ef4444" if diff > 0 else ("#10b981" if diff < 0 else "white")
    arrow = "▲" if diff > 0 else ("▼" if diff < 0 else "-")
    
    today_open = float(last['Open'])
    today_high = float(last['High'])
    today_low = float(last['Low'])
    today_volume = last['Volume']
    vol_ma5 = last['Vol_MA5']
    
    vol_ratio = (today_volume / vol_ma5) if vol_ma5 > 0 else 1
    vol_ratio_pct = round(vol_ratio * 100, 1)

    # 1. 莊家防守成本線計算
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
    except Exception:
        weighted_support = round(current_price * 0.95, 1)

    # 2. 量能動態標籤判定
    if vol_ratio > 1.5:
        vol_diag_msg = "⚡ 量能爆發"
        vol_diag_card_info = ("⚡ 【量能爆發】", "多空強烈表態，留意高階突破動能！", "success")
    elif vol_ratio < 0.7:
        is_above_ma5 = current_price >= last['MA5']
        is_strong_rsi = last['RSI'] >= 50
        inst_percent = a_data['法人持股'] if (a_data and a_data['法人持股'] != 'N/A') else 0
        if is_above_ma5 and (is_strong_rsi or inst_percent > 15):
            vol_diag_msg = "💎 大戶惜售 / 籌碼鎖定"
            vol_diag_card_info = (
                "💤 【量能明顯萎縮】",
                "💎 診斷：【大戶惜售 / 籌碼鎖定】\n\n• 現狀分析：量能大幅萎縮，但價格頑強守在 MA5 防線之上，顯示籌碼已被莊家大戶鎖死，散戶賣壓基本出盡。\n• 戰術提示：此處的突破有 90% 以上為「洗盤後的真突破」。建議沿著 MA5 / MA10 移動停利，偏多看待。",
                "warning"
            )
        else:
            vol_diag_msg = "🥶 人氣退潮"
            vol_diag_card_info = (
                "💤 【量能明顯萎縮】",
                "🥶 診斷：【人氣退潮 / 無人關注】\n\n• 現狀分析：量能萎縮且股價無力，跌破短期重要均線，市場炒作熱度退潮。\n• 戰術提示：此處拉高極大概率為「主力出貨的假突破」。建議嚴守紀律，切勿在此冒險接刀抄底。",
                "error"
            )
    else:
        vol_diag_msg = "⚖️ 量能溫和"
        vol_diag_card_info = ("⚖️ 【量能溫和】", "正常健康換手，股價沿著原有技術阻力平穩震盪中。", "info")

    # 3. 股票名稱與 RSI 狀態
    plot_df = df.tail(view_days)
    rsi_val = round(plot_df['RSI'].dropna().iloc[-1], 2) if not plot_df['RSI'].dropna().empty else 50.0
    inst_val = a_data.get('法人持股', 0) if a_data else 0
    chip_advice = " (大戶鎖碼中)" if inst_val > 25 else " (散戶主導中)"
    
    if rsi_val > 80: color, msg = "#ef4444", f"⚠️【高檔過熱：禁止追高{chip_advice}】"
    elif rsi_val < 40: color, msg = "#10b981", f"✅【低檔安全：留意佈局{chip_advice}】"
    else: color, msg = "#f59e0b", f"⚖️【區間震盪：觀望趨勢{chip_advice}】"

    current_dict = load_stock_dict()
    if clean_sid in current_dict:
        sname = current_dict[clean_sid]
        display_name = sname if clean_sid in sname else f"{clean_sid} {sname}"
    else:
        display_name = str(target_sid)

    # ==============================================================================
    # 🌟 【第 1 層：頂部全寬戰情大看板】
    # ==============================================================================
    st.markdown(f"""<div style="background: linear-gradient(90deg, #111827, #000000); border-left: 10px solid {color}; padding: 18px 25px; border-radius: 12px; display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 15px; margin-bottom: 15px; border-top: 1px solid #1e293b; border-right: 1px solid #1e293b; border-bottom: 1px solid #1e293b;">
<div style="min-width: 320px; display: flex; flex-direction: column; justify-content: space-between;">
<div style="display: flex; align-items: baseline; gap: 15px; margin-bottom: 5px;">
<h2 style="color:white; font-size: 32px; font-weight: 900; margin:0; letter-spacing: 1px;">{display_name}</h2>
<span style="font-size: 18px; color: {color}; font-weight: bold; background-color: rgba(255,255,255,0.05); padding: 2px 10px; border-radius: 20px;">RSI: {rsi_val}</span>
</div>
<p style="color:{color}; font-size: 20px; font-weight: bold; margin: 5px 0 0 0;">
{msg} <span style="color: #475569; margin: 0 10px;">|</span> 
<span style="color: #e2e8f0; font-size: 16px; background-color: #1e293b; padding: 4px 12px; border-radius: 6px; border: 1px solid #475569; display: inline-block; vertical-align: middle;">{vol_diag_msg}</span>
</p>
</div>
<div style="display: flex; align-items: center; gap: 20px; flex-wrap: wrap; justify-content: flex-end;">
<div style="text-align: right; padding-right: 20px; border-right: 2px solid #334155;">
<p style="color: #94a3b8; font-size: 12px; margin: 0 0 4px 0; font-weight: bold;">最新報價</p>
<div style="display: flex; align-items: baseline; gap: 10px; justify-content: flex-end;">
<span style="color: {price_color}; font-size: 38px; font-weight: 900; line-height: 1;">{round(current_price, 2)}</span>
<span style="color: {price_color}; font-size: 18px; font-weight: bold;">{arrow} {abs(diff)} ({diff_pct}%)</span>
</div>
</div>
<div style="display: flex; gap: 8px;">
 <div style="background-color: #1e293b; width: 75px; padding: 8px 5px; border-radius: 8px; border: 1px solid #94a3b8; text-align: center;">
 <p style="color: #cbd5e1; font-size: 11px; margin: 0;">昨收</p>
 <p style="color: #e2e8f0; font-size: 17px; font-weight: bold; margin: 4px 0 0 0;">{round(prev_price, 2)}</p>
 </div>
 <div style="background-color: #1e293b; width: 75px; padding: 8px 5px; border-radius: 8px; border: 1px solid #38bdf8; text-align: center;">
 <p style="color: #38bdf8; font-size: 11px; margin: 0;">開盤</p>
 <p style="color: white; font-size: 17px; font-weight: bold; margin: 4px 0 0 0;">{round(today_open, 2)}</p>
 </div>
 <div style="background-color: #1e293b; width: 75px; padding: 8px 5px; border-radius: 8px; border: 1px solid #ef4444; text-align: center;">
 <p style="color: #ef4444; font-size: 11px; margin: 0;">最高</p>
 <p style="color: white; font-size: 17px; font-weight: bold; margin: 4px 0 0 0;">{round(today_high, 2)}</p>
 </div>
 <div style="background-color: #1e293b; width: 75px; padding: 8px 5px; border-radius: 8px; border: 1px solid #10b981; text-align: center;">
 <p style="color: #10b981; font-size: 11px; margin: 0;">最低</p>
 <p style="color: white; font-size: 17px; font-weight: bold; margin: 4px 0 0 0;">{round(today_low, 2)}</p>
 </div>
</div>
</div>
</div>""", unsafe_allow_html=True)

    # ==============================================================================
    # 🌟 【第 2 層：核心交易雙屏對齊】
    # ==============================================================================
    col_chart, col_telemetry = st.columns([2.6, 1.4])
    
    with col_chart:
        bb_std = plot_df['Close'].rolling(20).std()
        bb_upper = plot_df['MA20'] + (bb_std * 2)
        bb_lower = plot_df['MA20'] - (bb_std * 2)

        macd_gold_cond = (plot_df['DIF'] > plot_df['DEA']) & (plot_df['DIF'].shift(1) <= plot_df['DEA'].shift(1))
        macd_dead_cond = (plot_df['DIF'] < plot_df['DEA']) & (plot_df['DIF'].shift(1) >= plot_df['DEA'].shift(1))
        kd_gold_cond = (plot_df['K'] > plot_df['D']) & (plot_df['K'].shift(1) <= plot_df['D'].shift(1))
        kd_dead_cond = (plot_df['K'] < plot_df['D']) & (plot_df['K'].shift(1) >= plot_df['D'].shift(1))
        vol_burst_cond = (plot_df['Close'] > plot_df['Open']) & (plot_df['Volume'] >= plot_df['Vol_MA5'] * 1.15)

        macd_gold_near = macd_gold_cond | macd_gold_cond.shift(1, fill_value=False) | macd_gold_cond.shift(-1, fill_value=False)
        kd_gold_near = kd_gold_cond | kd_gold_cond.shift(1, fill_value=False) | kd_gold_cond.shift(-1, fill_value=False)
        bull_resonance_cond = (kd_gold_cond & (macd_gold_near | (vol_burst_cond & (plot_df['MACD_Hist'] > plot_df['MACD_Hist'].shift(1))))) | (macd_gold_cond & kd_gold_near)
        bear_resonance_cond = kd_dead_cond & (macd_dead_cond | macd_dead_cond.shift(1, fill_value=False) | macd_dead_cond.shift(-1, fill_value=False))

        resonance_hover_texts = []
        for idx_dt in plot_df.index:
            tags = []
            if bull_resonance_cond.loc[idx_dt]: tags.append("🌟【多頭強烈共振】")
            elif bear_resonance_cond.loc[idx_dt]: tags.append("⚠️【雙死叉共振轉弱】")
            if vol_burst_cond.loc[idx_dt]: tags.append("🔥爆量攻擊")
            if macd_gold_cond.loc[idx_dt]: tags.append("🌊MACD活叉")
            elif macd_dead_cond.loc[idx_dt]: tags.append("❄️MACD死叉")
            if kd_gold_cond.loc[idx_dt]: tags.append("⚡KD活叉")
            elif kd_dead_cond.loc[idx_dt]: tags.append("❄️KD死叉")
            if plot_df.loc[idx_dt, 'RSI'] < 40: tags.append("💎RSI低檔區")
            elif plot_df.loc[idx_dt, 'RSI'] > 80: tags.append("🚨RSI過熱區")
            resonance_hover_texts.append(" + ".join(tags) if tags else "⚖️ 指標平穩運行")

        # ✅ 在建立圖表 (make_subplots) 之前，先算出最新的關鍵結構支撐位！
        weighted_support, support_logic_str = calculate_structural_support(df)
        fig = make_subplots(
            rows=5, cols=1, shared_xaxes=True, vertical_spacing=0.045,
            row_heights=[0.42, 0.145, 0.145, 0.145, 0.145],
            subplot_titles=(
                    f"📈 {display_name} K線、均線與關鍵結構支撐 ({weighted_support}元) [⭐ 金色虛線 = 多指標共振買點]",
                "📊 成交量與 5日均量動能 (紅漲綠跌・橘金爆量突破)",
                "🌊 MACD 波段趨勢動能 (▲ 活叉買點 / ▼ 死叉賣點 ➔ 滑鼠移上自動顯示)",
                "⚡ KD 隨機轉折指標 (▲ 活叉 / ▼ 死叉・80超買 / 20超賣)",
                "🎯 RSI (14) 相對強弱與背離監控 (80過熱警戒 / 40低檔超跌)"
            )
        )

        # 第 1 層：K線 + 均線 + 布林通道 + 莊家防線
        fig.add_trace(go.Candlestick(
            x=plot_df.index, open=plot_df['Open'], high=plot_df['High'],
            low=plot_df['Low'], close=plot_df['Close'], name="K線",
            decreasing=dict(fillcolor='#00e676', line=dict(color='#00e676')),
            increasing=dict(fillcolor='#ff3b5c', line=dict(color='#ff3b5c')),
            text=resonance_hover_texts
        ), row=1, col=1)
        fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df['MA5'], name="5MA", line=dict(color='#fb923c', width=1.5), hovertemplate="5MA: %{y:.2f}<extra></extra>"), row=1, col=1)
        fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df['MA10'], name="10MA", line=dict(color='#38bdf8', width=1.5), hovertemplate="10MA: %{y:.2f}<extra></extra>"), row=1, col=1)
        fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df['MA20'], name="20MA(月)", line=dict(color='#c084fc', width=1.8), hovertemplate="20MA: %{y:.2f}<extra></extra>"), row=1, col=1)
        fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df['MA60'], name="60MA(季)", line=dict(color='#2dd4bf', width=2.2), hovertemplate="60MA: %{y:.2f}<extra></extra>"), row=1, col=1)
        fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df['MA240'], name="240MA(年)", line=dict(color='#e2e8f0', width=2, dash='dot'), hovertemplate="240MA: %{y:.2f}<extra></extra>"), row=1, col=1)
        
        fig.add_trace(go.Scatter(x=plot_df.index, y=bb_upper, name="布林上軌", showlegend=False, line=dict(color='rgba(148, 163, 184, 0.4)', width=1, dash='dash'), hovertemplate="布林上軌: %{y:.2f}<extra></extra>"), row=1, col=1)
        fig.add_trace(go.Scatter(x=plot_df.index, y=bb_lower, name="布林下軌", showlegend=False, line=dict(color='rgba(148, 163, 184, 0.4)', width=1, dash='dash'), fill='tonexty', fillcolor='rgba(148, 163, 184, 0.04)', hovertemplate="布林下軌: %{y:.2f}<extra></extra>"), row=1, col=1)

        bull_res_df = plot_df[bull_resonance_cond]
        if not bull_res_df.empty:
            fig.add_trace(go.Scatter(
                x=bull_res_df.index, y=bull_res_df['Low'] * 0.985, mode='markers', name="⭐多指標共振",
                marker=dict(symbol='star', size=13, color='#facc15', line=dict(color='#000000', width=1)),
                hovertemplate="<b>🌟【多指標黃金共振買點】</b><br>KD + MACD/量能同步轉強！<extra></extra>"
            ), row=1, col=1)
            for res_dt in bull_res_df.index:
                fig.add_vline(x=res_dt, line_width=1.2, line_dash="dot", line_color="rgba(250, 204, 21, 0.35)")

        

        # 2. 優化關鍵支撐水平線：線條調細並半透明化，標籤移至左側並加上深色半透明底框防重疊
        fig.add_hline(
            y=weighted_support,
            line_dash="dash",
            line_color="rgba(245, 158, 11, 0.65)", # 👈 降低不透明度至 65%，不搶 K 線風采
            line_width=1.5,                        # 👈 線條改為 1.5px 更精緻
            annotation_text=f" 🛡️ 支撐 {weighted_support} ",
            annotation_position="top left",        # 👈 移至左側，徹底避開右側最新 K 棒與星星！
            annotation_font=dict(color="#FDE68A", size=11),
            annotation_bgcolor="rgba(15, 23, 42, 0.85)", # 👈 加上深色半透明底框，壓在K線上也清晰可讀
            annotation_bordercolor="#F59E0B",
            annotation_borderwidth=1,
            row=1, col=1
        )

        # 第 2 層：三色成交量 + 5日均量
        vol_colors = []
        vol_status_labels = []
        for idx_v, r_v in plot_df.iterrows():
            is_up = r_v['Close'] >= r_v['Open']
            is_burst = pd.notna(r_v['Vol_MA5']) and r_v['Vol_MA5'] > 0 and (r_v['Volume'] >= r_v['Vol_MA5'] * 1.15)
            if is_up and is_burst:
                vol_colors.append('#f59e0b')
                vol_status_labels.append("🔥 爆量紅K攻擊 (量比>=1.15x)")
            elif is_up:
                vol_colors.append('#ff3b5c')
                vol_status_labels.append("🔴 價漲紅K")
            else:
                vol_colors.append('#00e676')
                vol_status_labels.append("🟢 價跌黑K")

        fig.add_trace(go.Bar(
            x=plot_df.index, y=plot_df['Volume'], name="成交量", showlegend=False,
            marker_color=vol_colors, opacity=0.92, customdata=vol_status_labels,
            hovertemplate="成交量: <b>%{y:.1f} 張</b> (%{customdata})<extra></extra>"
        ), row=2, col=1)
        fig.add_trace(go.Scatter(
            x=plot_df.index, y=plot_df['Vol_MA5'], name="5日均量", showlegend=False,
            line=dict(color='#fef08a', width=2),
            hovertemplate="5日均量: %{y:.1f} 張<extra></extra>"
        ), row=2, col=1)

        # 第 3 層：MACD + 純圖標活叉/死叉
        m_colors = ['#ff3b5c' if x > 0 else '#00e676' for x in plot_df['MACD_Hist']]
        fig.add_trace(go.Bar(x=plot_df.index, y=plot_df['MACD_Hist'], name="MACD柱", showlegend=False, marker_color=m_colors, hovertemplate="MACD柱: %{y:.2f}<extra></extra>"), row=3, col=1)
        fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df['DIF'], name="DIF快線", showlegend=False, line=dict(color='#38bdf8', width=1.8), hovertemplate="DIF快線: %{y:.2f}<extra></extra>"), row=3, col=1)
        fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df['DEA'], name="DEA慢線", showlegend=False, line=dict(color='#facc15', width=1.8), hovertemplate="DEA慢線: %{y:.2f}<extra></extra>"), row=3, col=1)

        macd_gold = plot_df[macd_gold_cond]
        macd_dead = plot_df[macd_dead_cond]
        if not macd_gold.empty:
            fig.add_trace(go.Scatter(
                x=macd_gold.index, y=macd_gold['DIF'], mode='markers', name="MACD活叉", showlegend=False,
                marker=dict(symbol='triangle-up', size=12, color='#fde047', line=dict(color='#000000', width=1.2)),
                hovertemplate="<b>🔥【MACD 黃金活叉】</b>DIF 向上突破 DEA (波段轉強)<extra></extra>"
            ), row=3, col=1)
        if not macd_dead.empty:
            fig.add_trace(go.Scatter(
                x=macd_dead.index, y=macd_dead['DIF'], mode='markers', name="MACD死叉", showlegend=False,
                marker=dict(symbol='triangle-down', size=12, color='#06b6d4', line=dict(color='#000000', width=1.2)),
                hovertemplate="<b>❄️【MACD 死亡交叉】</b>DIF 向下跌破 DEA (波段轉弱)<extra></extra>"
            ), row=3, col=1)

        # 第 4 層：KD + 純圖標活叉/死叉
        fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df['K'], name="K值", showlegend=False, line=dict(color='#ffffff', width=1.8), hovertemplate="K值: %{y:.1f}<extra></extra>"), row=4, col=1)
        fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df['D'], name="D值", showlegend=False, line=dict(color='#facc15', width=1.8), hovertemplate="D值: %{y:.1f}<extra></extra>"), row=4, col=1)
        fig.add_hline(y=80, line_dash="dot", line_color="rgba(239, 68, 68, 0.5)", row=4, col=1)
        fig.add_hline(y=20, line_dash="dot", line_color="rgba(16, 185, 129, 0.5)", row=4, col=1)

        kd_gold = plot_df[kd_gold_cond]
        kd_dead = plot_df[kd_dead_cond]
        if not kd_gold.empty:
            fig.add_trace(go.Scatter(
                x=kd_gold.index, y=kd_gold['K'], mode='markers', name="KD活叉", showlegend=False,
                marker=dict(symbol='triangle-up', size=11, color='#fde047', line=dict(color='#000000', width=1.2)),
                hovertemplate="<b>⚡【KD 黃金活叉】</b>K值向上突破 D值 (短線轉強買點)<extra></extra>"
            ), row=4, col=1)
        if not kd_dead.empty:
            fig.add_trace(go.Scatter(
                x=kd_dead.index, y=kd_dead['K'], mode='markers', name="KD死叉", showlegend=False,
                marker=dict(symbol='triangle-down', size=11, color='#06b6d4', line=dict(color='#000000', width=1.2)),
                hovertemplate="<b>❄️【KD 死亡交叉】</b>K值向下跌破 D值 (短線轉弱調節)<extra></extra>"
            ), row=4, col=1)

        # 第 5 層：RSI (14) + 底背離
        fig.add_trace(go.Scatter(
            x=plot_df.index, y=plot_df['RSI'], name="RSI(14)", showlegend=False,
            line=dict(color='#c084fc', width=2),
            fill='tozeroy', fillcolor='rgba(192, 132, 252, 0.08)',
            customdata=resonance_hover_texts,
            hovertemplate="RSI(14): <b>%{y:.1f}</b><br>🔗 當日連動: <b>%{customdata}</b><extra></extra>"
        ), row=5, col=1)
        fig.add_hline(y=80, line_dash="dash", line_color="#ef4444", annotation_text="80 過熱", annotation_position="top right", annotation_font=dict(color="#ef4444", size=10), row=5, col=1)
        fig.add_hline(y=50, line_dash="dot", line_color="#64748b", row=5, col=1)
        fig.add_hline(y=40, line_dash="dash", line_color="#10b981", annotation_text="40 背離低接區", annotation_position="bottom right", annotation_font=dict(color="#10b981", size=10), row=5, col=1)

        for annotation in fig['layout']['annotations']:
            if annotation['text'].startswith(('📈', '📊', '🌊', '⚡', '🎯')):
                annotation['x'] = 0.0
                annotation['xanchor'] = 'left'
                annotation['y'] = annotation['y'] + 0.012
                annotation['font'] = dict(size=13.5, color='#38bdf8', family='Microsoft JhengHei')

        macd_max = max(plot_df['DIF'].abs().max(), plot_df['DEA'].abs().max(), plot_df['MACD_Hist'].abs().max(), 1.0) * 1.25
        fig.update_yaxes(range=[-macd_max, macd_max], row=3, col=1)
        fig.update_yaxes(range=[-8, 112], row=4, col=1)
        fig.update_yaxes(range=[5, 98], row=5, col=1)

        fig.update_traces(xaxis="x5")

        fig.update_layout(
            height=1100,
            template="plotly_dark",
            hovermode="x unified",
            spikedistance=-1,
            hoverdistance=-1,
            legend=dict(orientation="h", yanchor="bottom", y=1.05, xanchor="left", x=0, font=dict(size=12.5)),
            margin=dict(l=10, r=50, t=40, b=10)
        )
        
        fig.update_xaxes(rangeslider_visible=False)
        fig.update_xaxes(showticklabels=False, row=1, col=1)
        fig.update_xaxes(showticklabels=False, row=2, col=1)
        fig.update_xaxes(showticklabels=False, row=3, col=1)
        fig.update_xaxes(showticklabels=False, row=4, col=1)
        fig.update_xaxes(
            showticklabels=True,
            showspikes=True,
            spikemode="across",
            spikesnap="cursor",
            spikecolor="#facc15",
            spikethickness=1.5,
            spikedash="dash",
            row=5, col=1
        )
        fig.update_yaxes(showspikes=True, spikecolor="#64748b", spikethickness=1, spikedash="dot")
        
        st.plotly_chart(
            fig,
            use_container_width=True,
            config={"displayModeBar": False}
        )

    with col_telemetry:
        # 1. 買賣掛單監控
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

        # 2. 量能動態診斷
        st.divider()
        st.subheader("📊 量能動態診斷")
        
        col_v1, col_v2, col_v3 = st.columns(3)
        with col_v1:
            st.metric("今日成交量 (張)", f"{int(today_volume):,}")
        with col_v2:
            st.metric("5日均量 (張)", f"{int(vol_ma5):,}")
        with col_v3:
            delta_color = "normal" if vol_ratio_pct > 115 else ("inverse" if vol_ratio_pct < 70 else "off")
            st.metric("量能佔比", f"{vol_ratio_pct}%", delta=f"{round(vol_ratio_pct-100, 1)}%", delta_color=delta_color)
            
        custom_diagnostic_card(vol_diag_card_info[0], vol_diag_card_info[1], vol_diag_card_info[2])

        # 3. 關鍵支撐位與技術狀態 (🌟 內建反當沖純價格結構與 ATR 支撐引擎，免去其他地方貼函數！)
        st.divider()
        st.subheader("🛡️ 關鍵支撐位與技術指標")
        
        # 直接計算並覆蓋 weighted_support，下方 3-3-4 建倉與 AI 戰略官會自動同步使用此新支撐！
        weighted_support, support_logic_str = calculate_structural_support(df)
        buffer_pct = round(((current_price - weighted_support) / current_price) * 100, 2) if current_price > 0 else 0.0
        
        if current_price >= weighted_support:
            custom_diagnostic_card(
                "🛡️ 關鍵結構支撐位",
                f"🟢 支撐守住 ({weighted_support} 元) ｜ 📏 安全緩衝：+{buffer_pct}%\n"
                f"📐 結構依據：{support_logic_str}\n"
                f"💡 診斷：已剔除當沖虛胖量能干擾，收盤價穩守於波段留倉結構之上，趨勢健康！",
                "success"
            )
        else:
            custom_diagnostic_card(
                "🛡️ 關鍵結構支撐位",
                f"🔴 支撐失守 ({weighted_support} 元) ｜ 📏 跌破深度：{buffer_pct}%\n"
                f"📐 結構依據：{support_logic_str}\n"
                f"💡 診斷：收盤實質擊穿波段留倉成本與合理波動下限，多頭結構破壞，切忌盲目接刀！",
                "error"
            )

        has_divergence = False
        if len(df) >= 10:
            past_min_close = df.iloc[-10:-1]['Close'].min()
            past_min_rsi = df.iloc[-10:-1]['RSI'].min()
            if (current_price <= past_min_close) and (last['RSI'] > past_min_rsi) and (last['RSI'] < 40):
                has_divergence = True
        
        if has_divergence:
            custom_diagnostic_card("🔥 偵測到【低檔底背離】", "股價創波段新低但 RSI 拒絕破底，下跌力竭、大戶低吸，醞釀強彈！", "warning")

        st.markdown(f"""
        <div style="background-color: #0f172a; padding: 10px 14px; border-radius: 8px; border: 1px solid #334155; font-size: 13.5px; line-height: 1.8; color: #cbd5e1;">
            <b>均線：</b> 5MA: <span style="color:orange;">{round(last['MA5'], 1)}</span> | 10MA: <span style="color:#60a5fa;">{round(last['MA10'], 1)}</span> | 20MA: <span style="color:violet;">{round(last['MA20'], 1)}</span><br>
            <b>指標：</b> MACD: {'🟢 金叉' if last['DIF'] > last['DEA'] else '🔴 死叉'} | KD: {'🟢 金叉' if last['K'] > last['D'] else '🔴 死叉'}
        </div>
        """, unsafe_allow_html=True)
    # ==============================================================================
    # 🌟 【第 3 層：全寬深度決策戰情室】
    # ==============================================================================
    st.divider()
    st.subheader("📊 籌碼流向、基本面毛利與實戰決策")
    
    col_chip_card, col_fin_card = st.columns(2)
    
    with col_chip_card:
        chip_results = get_institutional_chips(clean_sid, df)
        custom_diagnostic_card(
            chip_results["inst_status"],
            "【三大法人資金與籌碼流向診斷】\n\n"
            f"🚀 近 5 日主力籌碼淨向： {chip_results['net_buy_5d']}\n"
            f"📊 近 10 日主力籌碼淨向： {chip_results['net_buy_10d']}\n\n"
            f"💡 籌碼解讀： {chip_results['major_force_status']}",
            chip_results["inst_card_type"]
        )

    with col_fin_card:
        fin_trend = get_financial_margin_trend(clean_sid)
        if a_data:
            eps_val = a_data.get('EPS', 'N/A')
            roe_val = a_data.get('ROE', 'N/A')
            pe_val = a_data.get('本益比', 'N/A')   
            debt_val = a_data.get('負債比')
            inst_hold = a_data.get('法人持股')
            debt_text = f"{round(debt_val, 1)}%" if (debt_val and isinstance(debt_val, (int, float)) and debt_val != 0) else "N/A"
            
            ann_gm_str = " ➔ ".join([f"{k[-2:]}年:{v}%" for k, v in fin_trend["annual_gm_dict"].items()]) if fin_trend["annual_gm_dict"] else f"最新: {fin_trend['latest_gm']}"
            card_color = "success" if fin_trend["is_long_term_growth"] else "warning"

            custom_diagnostic_card(
                f"🏢 核心財報與毛利趨勢：{fin_trend['status_tag']}",
                f"📈 歷年毛利率軌跡： {ann_gm_str}\n"
                f"🎯 跨年成長診斷： {fin_trend['diagnosis_text']}\n"
                f"───────────────\n"
                f"👥 法人大戶持股比： {round(inst_hold, 1) if (inst_hold and isinstance(inst_hold, (int,float))) else '0.0'}%  |  💵 預估年化 EPS： {eps_val} 元\n"
                f"📊 股東權益報酬 ROE： {roe_val}  |  ⚡ 預估本益比 PE： {pe_val} 倍\n"
                f"⚖️ 企業負債比率： {debt_text}",
                card_color
            )
            
            if fin_trend["annual_gm_dict"] or fin_trend["quarterly_gm_dict"]:
                with st.expander("📊 點擊展開【跨年度 vs 近四季毛利率】對照圖（檢視單季淡旺季與全年趨勢）"):
                    t_col1, t_col2 = st.columns(2)
                    with t_col1:
                        st.caption("📅 近幾年【整年度】毛利率趨勢 (%)")
                        if fin_trend["annual_gm_dict"]:
                            st.bar_chart(pd.Series(fin_trend["annual_gm_dict"], name="年度毛利率(%)"))
                    with t_col2:
                        st.caption("📆 最近四季【單季】毛利率波動 (%)")
                        if fin_trend["quarterly_gm_dict"]:
                            st.line_chart(pd.Series(fin_trend["quarterly_gm_dict"], name="單季毛利率(%)"))

    # 風報比與 3-3-4 建倉試算
    st.divider()
    st.subheader("🎯 實戰買進決策與風報比試算")
    
    ma5_val = round(float(last['MA5']), 2) if pd.notna(last['MA5']) else current_price
    ma20_val = round(float(last['MA20']), 2) if pd.notna(last['MA20']) else current_price
    ma60_val = round(float(last['MA60']), 2) if pd.notna(last['MA60']) else current_price
    
    bias_20 = round(((current_price - ma20_val) / ma20_val) * 100, 2) if ma20_val > 0 else 0.0
    ma_max = max(ma5_val, float(last['MA10']), ma20_val)
    ma_min = min(ma5_val, float(last['MA10']), ma20_val)
    ma_spread_pct = round(((ma_max - ma_min) / ma_min) * 100, 2) if ma_min > 0 else 99.0
    
    high_60d = round(float(df.tail(60)['High'].max()), 2)
    upside_pct = max(round(((high_60d - current_price) / current_price) * 100, 2), 1.0)
    downside_pct = max(round(((current_price - weighted_support) / current_price) * 100, 2), 1.0)
    rr_ratio = round(upside_pct / downside_pct, 2)
    
    col_rr, col_entry = st.columns(2)
    with col_rr:
        if bias_20 > 15.0:
            rr_tag = "⚠️ 短線正乖離過大（嚴禁追高）"
            rr_color = "error"
        elif ma_spread_pct <= 3.0 and current_price >= ma20_val:
            rr_tag = "🌟 均線極致糾結突破（黃金起漲點）"
            rr_color = "success"
        elif rr_ratio >= 2.0 and current_price >= weighted_support:
            rr_tag = f"✅ 風報比極佳（盈虧比 1 : {rr_ratio}）"
            rr_color = "success"
        else:
            rr_tag = f"⚖️ 區間博弈位階（盈虧比 1 : {rr_ratio}）"
            rr_color = "info"
            
        custom_diagnostic_card(
            f"📐 位階與風報比：{rr_tag}",
            f"📏 月線乖離率 (20MA BIAS)： {bias_20:+.2f}%  |  🔗 均線糾結度： {ma_spread_pct}%\n"
            f"🎯 上檔前高空間 ({high_60d}元)： +{upside_pct}%  |  🛡️ 下檔防線風險 ({weighted_support}元)： -{downside_pct}%\n"
            f"💡 實戰判定： {'均線糾結壓縮完成，具備波段爆發力！' if ma_spread_pct <= 3.0 else ('正乖離過熱，建議等待拉回月線再佈局。' if bias_20 > 15 else '嚴守關鍵結構支撐，盈虧比大於 2 倍時具高期望值。')}",
            rr_color
        )
        
    with col_entry:
        p1_price = round(min(current_price, ma5_val), 2)
        p2_price = ma20_val
        p3_price = round(max(ma60_val, weighted_support), 2)
        stop_loss_price = round(weighted_support * 0.97, 2)
        
        custom_diagnostic_card(
            "🪜 3-3-4 機構分批建倉與停損試算",
            f"🥇 第一批試單 (30% 資金・5MA 動能區)： 約 {p1_price} 元\n"
            f"🥈 第二批加碼 (30% 資金・20MA 月線支撐)： 約 {p2_price} 元\n"
            f"🥉 第三批重倉 (40% 資金・關鍵結構支撐)：約 {p3_price} 元\n" # 👈 將莊家防線改為關鍵結構支撐
            f"🛑 鐵血停損線 (收盤實質跌破支撐 3%)： {stop_loss_price} 元",    # 👈 同步修改防線為支撐
            "warning"
        )

    # ==========================================================================
    # 🧬 互動展開面板：K 線雙胞胎潛力股檢索器
    # ==========================================================================
    with st.expander(f"🧬 點擊展開：尋找全市場與【{sid}】線型相似的潛力飆股"):
        st.caption("利用 Z-Score 型態比對與時光機基因回推，在全市場尋找起漲前蓄勢或走勢高度同步的雙胞胎標的。")
        
        col_ex1, col_ex2, col_ex3 = st.columns(3)
        with col_ex1:
            match_mode = st.selectbox(
                "比對策略模式", 
                ["時光機：比對起漲前蓄勢段 (Lag 10天)", "同步型態：比對當下近20日走勢"],
                index=0
            )
        with col_ex2:
            comparison_window = st.slider("比對天數 (Window)", min_value=10, max_value=40, value=20, step=5)
        with col_ex3:
            st.write("")
            st.write("")
            search_button = st.button("🚀 開始全市場掃描雙胞胎", use_container_width=True)

        if search_button:
            with st.spinner(f"正在從全市場候選池計算與 {sid} 的型態相關係數..."):
                # 取得目前全市場候選股票代號清單 (從您的 stock_dict 或 market_dict 獲取)
                all_candidates = [f"{k}.TW" if not k.endswith(('.TW', '.TWO')) else k for k in stock_dict.keys()][:300] # 取前300大或全市場
                
                # 決定是否啟用時光機倒帶
                lag_val = 10 if "時光機" in match_mode else 0
                target_ticker = f"{sid}.TW" if not sid.endswith(('.TW', '.TWO')) else sid
                
                twins_results = find_kline_twins(
                    target_sid=target_ticker,
                    candidate_tickers=all_candidates,
                    window=comparison_window,
                    lag_days=lag_val,
                    top_n=5
                )

            if twins_results:
                st.success(f"✨ 成功找到 {len(twins_results)} 檔型態高度神似的潛在標的！")
                
                # 轉為表格美化呈現
                import pandas as pd
                df_twins = pd.DataFrame(twins_results)
                df_twins.columns = ["股票代號", "相似度 (%)", "現價 (元)", "5日均量 (張)", "季線乖離 (%)"]
                st.dataframe(df_twins, use_container_width=True, hide_index=True)
            else:
                st.warning("⚠️ 目前在候選池中未找到相似度達 80% 以上且符合 60MA 多頭結構的股票，可嘗試調整比對天數。")
    # 🧠 一鍵召喚 Gemini AI 實戰買賣決策官
    if st.button("🧠 召喚黑馬 AI 戰略官：產出今日買賣決策報告 (消耗 1 次額度)", use_container_width=True):
        with st.spinner("🤖 黑馬戰略官正在綜合【技術乖離 + 主力籌碼 + 跨年毛利】進行深度推演..."):
            try:
                ai_model = genai.GenerativeModel("gemini-2.5-flash")
                inst_hold_val = a_data.get('法人持股', 0) if a_data else 0
                ann_gm_text = " ➔ ".join([f"{k[-2:]}年:{v}%" for k, v in fin_trend["annual_gm_dict"].items()]) if fin_trend["annual_gm_dict"] else f"最新: {fin_trend['latest_gm']}"
                
                decision_prompt = f"""
                你現在是『🐎 黑馬雷達』首席量化操盤手。請根據以下【確切已知事實】為吳秉諺產出簡潔犀利的買賣決策報告：
                - 標的：{display_name}，現價：{current_price} 元（漲跌：{diff_pct}%）
                - 均線與指標：5MA={ma5_val}, 20MA={ma20_val} (月線乖離率 {bias_20}%), 60MA={ma60_val}, RSI={rsi_val}, 均線糾結度={ma_spread_pct}%
                - 量價與防線：今日量比={round(vol_ratio, 2)}x ({vol_diag_msg})，關鍵結構支撐={weighted_support}元，盈虧比=1:{rr_ratio}
                - 籌碼流向：近5日主力淨向={chip_results['net_buy_5d']} ({chip_results['inst_status']})，法人持股={round(inst_hold_val, 1) if isinstance(inst_hold_val, (int, float)) else 0}%
                - 財報與毛利趨勢：{fin_trend['status_tag']}，歷年毛利={ann_gm_text}，營業利益率={fin_trend['latest_opm']}%，診斷={fin_trend['diagnosis_text']}
                
                請以繁體中文輸出 3 點結論（不超過 250 字，嚴禁模糊推測）：
                1. 【多空位階總評】：（明確給出：積極買進 / 拉回分批佈局 / 觀望勿追 / 逢高減碼）
                2. 【核心判斷依據】：（結合毛利保護傘、籌碼鎖碼與乖離率說明原因）
                3. 【具體操作紀律】：（給出進場參考價、加碼條件與鐵血停損價）
                """
                ai_resp = ai_model.generate_content(decision_prompt)
                st.info(ai_resp.text)
            except Exception as ex:
                st.error(f"AI 決策官連線異常：{ex}")

    # ==============================================================================
    # 🌟 【第 4 層：底部戰情推播控制台】
    # ==============================================================================
    st.divider() 
    st.markdown("""<div style="background: linear-gradient(135deg, #1e293b, #0f172a); padding: 18px 20px; border-radius: 12px; border: 1px solid #475569; margin-top: 10px;">
    <h3 style="color: #60a5fa; margin: 0 0 10px 0; font-size: 20px; display: flex; align-items: center; gap: 8px;">📡 戰情推播控制台</h3>
    </div>""", unsafe_allow_html=True)

    col_test_btn, col_scan_btn = st.columns(2)

    with col_test_btn:
        if st.button("🔗 發送 Discord 測試訊息", use_container_width=True, help="手動測試網頁與您的 Discord 頻道是否成功對接。"):
            tz_tw = datetime.timezone(datetime.timedelta(hours=8))
            test_time = datetime.datetime.now(tz_tw).strftime('%Y-%m-%d %H:%M:%S')
            test_embed = {
                "title": "✅ 秉諺的黑馬雷達連線測試",
                "description": "網頁主端控制台發送成功！手動推播管道運作良好。",
                "color": 3447003,
                "footer": {"text": f"測試時間: {test_time}"}
            }
            success, msg = send_discord_webhook(DEFAULT_DISCORD_WEBHOOK, test_embed)
            if success:
                st.success("✅ " + msg)
            else:
                st.error("❌ " + msg)

    with col_scan_btn:
        if st.button("🔍 執行全體雷達大掃描", use_container_width=True, help="立即對您自選清單裡的所有股票進行技術、籌碼與跨年毛利訊號的全面掃描。"):
            with st.spinner("🚀 雷達深度掃描與毛利趨勢運算中..."):
                daily_candidates = []
                current_scan_dict = load_stock_dict()
                for sid, sname in current_scan_dict.items():
                    res = run_single_scan_signal(sid, sname, DEFAULT_DISCORD_WEBHOOK)
                    if isinstance(res, dict) and 'score' in res:
                        daily_candidates.append(res)
                    time.sleep(0.2)
                
                if daily_candidates:
                    daily_candidates.sort(key=lambda x: x.get('score', 0), reverse=True)
                    
                    for stock in daily_candidates:
                        log_signal_to_csv(stock['sid'], stock['sname'], stock['current_price'], stock['embed'])
                    
                    top_targets = [s for s in daily_candidates if s.get('score', 0) >= 25.0][:5]
                    for stock in top_targets:
                        send_discord_webhook(DEFAULT_DISCORD_WEBHOOK, stock['embed'])
                        time.sleep(0.5)
                    
                    st.success(f"🎉 掃描完成！共偵測到 {len(daily_candidates)} 檔訊號，已將達標精華 Top {len(top_targets)} 推播至 Discord。")
                    st.toast(f"✅ 成功推送 Top {len(top_targets)} 檔黑馬至 Discord！", icon="🚀")
                    st.balloons()
                    time.sleep(2.5)
                    st.rerun()
                else:
                    st.info("💡 目前所有標的指標平穩，未達警報標準。")
                    st.toast("💤 掃描完畢，目前無異常訊號。", icon="☕")

else:
    st.error("❌ 暫時無法加載技術數據，請確認標的代號。")
