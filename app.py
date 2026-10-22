# ==============================================================================
# 🐎 秉諺的黑馬雷達 V42.5 - 網頁儀表板主程式 (終極瘦身旗艦版)
# ==============================================================================
import streamlit as st
import google.generativeai as genai
import os
import re
import json
import pandas as pd
from streamlit_autorefresh import st_autorefresh
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import yfinance as yf
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import requests
import datetime
import time

st.set_page_config(layout="wide", page_title="秉諺的黑馬雷達 V42.5")

# --- 背景自動刷新設定 ---
count = st_autorefresh(interval=300000, key="f5_refresh")

GEMINI_API_KEY = st.secrets.get("GEMINI_API_KEY") or os.environ.get("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    st.error("❌ 偵測不到 API 金鑰！請至 Streamlit Cloud Secrets 設定 'GEMINI_API_KEY'")
    st.stop()
else:
    genai.configure(api_key=GEMINI_API_KEY)

# --- 全域時間與看盤時段判定 ---
now = datetime.datetime.now()
is_weekday = now.weekday() < 5
is_trading_hours = datetime.time(9, 0) <= now.time() <= datetime.time(13, 35)

DICT_FILE = "watchlist.json"
INDUSTRY_DB_FILE = "industry_db.json"
DEFAULT_DISCORD_WEBHOOK = os.environ.get("DISCORD_WEBHOOK") or ""
WATCHLIST_CLOUD_KEY = "__WATCHLIST_DATA__"

DEFAULT_STOCKS = {
    "2330": "台積電", "2454": "聯發科", "8299": "群聯", "6147": "頎邦", "3711": "日月光投控",
    "2449": "京元電子", "6770": "力積電", "6510": "精測", "6849": "奇鼎", "5297": "廣化",
    "7853": "政美應用", "3595": "山太士", "2317": "鴻海", "2382": "廣達", "3231": "緯創",
    "2376": "技嘉", "2308": "台達電", "3017": "奇鋐", "3324": "雙鴻", "2377": "微星",
    "2345": "智邦", "3450": "聯鈞", "3363": "上詮", "6442": "光聖", "6451": "訊芯-KY",
    "3163": "波若威", "4979": "華星光", "3081": "聯亞", "2455": "全新", "3533": "嘉澤",
    "2059": "川湖", "2359": "所羅門", "2327": "國巨", "3037": "欣興", "4958": "臻鼎-KY",
    "3715": "定穎投控", "1815": "富喬", "2486": "一銓", "6282": "康舒", "1504": "東元",
    "6477": "安集", "2634": "漢翔", "2002": "中鋼", "2408": "南亞科", "2409": "友達",
    "3714": "富采", "1303": "南亞", "2105": "正新", "1802": "台玻", "9921": "巨大"
}

# ==============================================================================
# ☁️ 雲端資料庫雙向同步引擎
# ==============================================================================
def get_google_sheet():
    creds_dict = json.loads(st.secrets["GSPREAD_JSON"])
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(creds)
    return client.open_by_url(st.secrets["SHEET_URL"]).sheet1

def sync_all_to_cloud(industry_db_dict, watchlist_dict=None):
    try:
        clean_db = {str(k): v for k, v in industry_db_dict.items() if str(k) != WATCHLIST_CLOUD_KEY}
        with open("industry_db.json", "w", encoding="utf-8") as f:
            json.dump(clean_db, f, ensure_ascii=False, indent=4)
        
        if watchlist_dict is not None:
            pure_wl = {str(k): v for k, v in watchlist_dict.items() if "(⚡雷達)" not in str(v)}
            with open("watchlist.json", "w", encoding="utf-8") as f:
                json.dump(pure_wl, f, ensure_ascii=False, indent=4)
        else:
            if os.path.exists("watchlist.json"):
                with open("watchlist.json", "r", encoding="utf-8") as f:
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
    cloud_wl, cloud_db = {}, {}
    try:
        sheet = get_google_sheet()
        records = sheet.get_all_records()
        for row in records:
            sid_key = str(row.get('sid', '')).strip()
            raw_json = row.get('data', '')
            if not sid_key or not raw_json: continue
            if sid_key == WATCHLIST_CLOUD_KEY:
                cloud_wl = json.loads(raw_json)
            else:
                cloud_db[sid_key] = json.loads(raw_json)
    except Exception:
        pass

    local_db = {}
    if os.path.exists("industry_db.json"):
        try:
            with open("industry_db.json", "r", encoding="utf-8") as f:
                local_db = json.load(f)
        except Exception:
            pass
    merged_db = {**local_db, **cloud_db}

    try:
        with open("industry_db.json", "w", encoding="utf-8") as f:
            json.dump(merged_db, f, ensure_ascii=False, indent=4)
    except Exception:
        pass
    return cloud_wl, merged_db

def load_industry_db():
    _, merged_db = load_cloud_master_data()
    return merged_db

def migrate_local_to_cloud():
    _, merged_db = load_cloud_master_data()
    current_wl = st.session_state.get('STOCK_DICT', load_stock_dict())
    if sync_all_to_cloud(merged_db, current_wl):
        st.success(f"✅ 雙向智慧同步完成！雲端已永久保存 {len(current_wl)} 檔自選股與 {len(merged_db)} 筆 AI 百科！")
    else:
        st.error("❌ 雲端同步失敗，請檢查 Secrets 設定。")

def load_full_market():
    for fname in ["full_market_dict.json", "stock_dict.json"]:
        if os.path.exists(fname):
            try:
                with open(fname, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
    return {}

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
        except Exception:
            pass
    try:
        cloud_wl, db = load_cloud_master_data()
        if cloud_wl and isinstance(cloud_wl, dict):
            for k, v in cloud_wl.items():
                pure_name = str(v).replace(str(k), "").replace("台股代號", "").replace("(", "").replace(")", "").strip()
                current_data[str(k)] = f"{k} ({pure_name})"
        for sid, info in db.items():
            sid_str = str(sid).strip()
            if sid_str not in current_data and sid_str != WATCHLIST_CLOUD_KEY:
                company_name = info.get("name", "未知名稱").replace("台股代號 ", "")
                if sid_str in company_name:
                    current_data[sid_str] = company_name
                else:
                    current_data[sid_str] = f"{sid_str} ({company_name})"
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
    try:
        pure_data = {str(k): v for k, v in data.items() if "(⚡雷達)" not in str(v)}
        with open(DICT_FILE, "w", encoding="utf-8") as f:
            json.dump(pure_data, f, ensure_ascii=False, indent=4)
        current_db = st.session_state.get('INDUSTRY_DB', load_industry_db())
        sync_all_to_cloud(current_db, pure_data)
        return True
    except Exception:
        return False

# ==============================================================================
# 🤖 AI 決策與百科引擎
# ==============================================================================
def generate_ai_insights(company_name, summary):
    import json
    import re
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
        available_models = [m.name.replace("models/", "") for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
    except Exception:
        available_models = ['gemini-2.5-flash']

    priorities = ['gemini-3.8-flash', 'gemini-2.5-flash', 'gemini-1.5-pro', 'gemini-pro']
    run_list = [m for m in priorities if m in available_models]
    if not run_list: run_list = available_models[:3]

    last_err = ""
    for model_name in run_list:
        try:
            model = genai.GenerativeModel(model_name=model_name, generation_config={"response_mime_type": "application/json"})
            response = model.generate_content(prompt)
            text = response.text.strip()
            text = re.sub(r'^```(?:json)?\s*|\s*```$', '', text, flags=re.IGNORECASE)
            ai_dict = json.loads(text)
            ai_dict['source_url'] = source_url
            return ai_dict
        except Exception as e:
            last_err = str(e)
            if "429" in last_err or "quota" in last_err.lower() or "404" in last_err: continue
            break

    return {
        "company_brief": f"⚠️ 解析中斷: {last_err}", "overview": "【資料不足，無法確認】",
        "value_chain": "【資料不足，無法確認】", "competitors": [], "drivers": "【資料不足，無法確認】",
        "source_url": source_url
    }

def auto_update_industry_db(sid):
    sid = str(sid).strip()
    _, db = load_cloud_master_data()
    current_dict = st.session_state.get('STOCK_DICT', STOCK_DICT)
    company_name = current_dict.get(sid, f"台股代號 {sid}")
    
    prompt_context = "請提供以下台股公司的產業分析 (JSON格式: company_brief, overview, value_chain, competitors, drivers)。"
    ai_data = generate_ai_insights(company_name, prompt_context)
    
    if ai_data and not str(ai_data.get("company_brief", "")).startswith("⚠️ 解析"):
        db[sid] = {
            "name": company_name, "company_brief": ai_data.get("company_brief", ""),
            "overview": ai_data.get("overview", ""), "value_chain": ai_data.get("value_chain", ""),
            "competitors": ai_data.get("competitors", []), "drivers": ai_data.get("drivers", ""),
            "source_url": ai_data.get("source_url", ""), "last_updated": datetime.date.today().isoformat()
        }
        sync_all_to_cloud(db, current_dict)
        st.session_state['INDUSTRY_DB'] = db
        return True, f"✅ {company_name} 更新並自動同步至雲端成功"
    return False, ai_data.get("company_brief", "AI 解析失敗") if ai_data else "AI 解析失敗"

# ==============================================================================
# 📊 量化運算與技術指標引擎
# ==============================================================================
def log_signal_to_csv(sid, sname, price, embed):
    log_file = "signal_history.csv"
    tz_tw = datetime.timezone(datetime.timedelta(hours=8))
    now_time = datetime.datetime.now(tz_tw).strftime('%Y-%m-%d %H:%M:%S')
    file_exists = os.path.isfile(log_file)
    try:
        pure_sname = sname.split("(")[1].split(")")[0] if "(" in sname else sname
        desc = embed.get("description", "").replace("*", "").replace("`", "").replace("\n", " | ")
        tech_vol = ""
        for field in embed.get("fields", []):
            if "技術" in field.get("name", ""):
                tech_vol = field.get("value", "").replace("\n", " | ").replace("`", "")
        with open(log_file, mode='a', encoding='utf-8-sig', newline='') as f:
            if not file_exists: f.write("日期時間,股票代號,股票名稱,觸發價格,核心訊號,技術與量能\n")
            f.write(f"{now_time},{sid},{pure_sname},{price},{desc.replace(',', '，')},{tech_vol.replace(',', '，')}\n")
    except Exception:
        pass

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
                if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
                df = df.dropna(subset=['Close'])
                df = df[(df['Volume'] > 0) & (df['Volume'].notna())]
                df['Volume'] = df['Volume'] / 1000.0

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
                        if today_date.weekday() == 5: today_date -= datetime.timedelta(days=1)
                        elif today_date.weekday() == 6: today_date -= datetime.timedelta(days=2)
                        
                        last_k_date = df.index[-1].date()
                        if last_k_date < today_date and latest_price > 0:
                            new_timestamp = pd.Timestamp(today_date).tz_localize(df.index.tz)
                            df.loc[new_timestamp] = [latest_open, latest_high, latest_low, latest_price, latest_vol]
                        else:
                            if latest_price > 0:
                                df.loc[today_idx, 'Close'] = latest_price
                                if f_info['open']: df.loc[today_idx, 'Open'] = latest_open
                                if f_info['day_high']: df.loc[today_idx, 'High'] = latest_high
                                if f_info['day_low']: df.loc[today_idx, 'Low'] = latest_low
                                if f_info['last_volume']: df.loc[today_idx, 'Volume'] = latest_vol
                except Exception:
                    pass

                if df.empty or len(df) < 20: continue

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
                df['K'] = (100 * ((df['Close'] - low_9) / denom_kd)).ewm(com=2, adjust=False).mean()
                df['D'] = df['K'].ewm(com=2, adjust=False).mean()
                
                delta = df['Close'].diff()
                gain = (delta.where(delta > 0, 0)).rolling(14).mean()
                loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
                df['RSI'] = 100 - (100 / (1 + (gain / loss.replace(0, 0.00001))))
                return df
        except Exception:
            continue
    st.sidebar.error(f"❌ 無法抓取資料: {sid}") 
    return default_df

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
        if not historical_data.empty: quote["prev_close"] = float(historical_data.iloc[-1]['Close'])
        else: quote["prev_close"] = float(df.iloc[-2]['Close'])
    return quote

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
                    "EPS": eps_val if eps_val else "N/A", "營收成長率": info.get('revenueGrowth', 0),
                    "負債比": info.get('debtToEquity', 0),
                    "ROE": f"{round(info.get('returnOnEquity', 0)*100, 2)}%" if info.get('returnOnEquity') else "N/A",
                    "本益比": round(info.get("trailingPE", 0), 2) if info.get("trailingPE") else "N/A",
                    "法人持股": (info.get("heldPercentInstitutions", 0) or 0) * 100
                }
        except Exception:
            continue
    return None 

@st.cache_data(ttl=3600)
def get_financial_margin_trend(sid):
    sid = str(sid).split('(')[0].split(' ')[0].strip()
    if ".TW" in sid.upper() or ".TWO" in sid.upper(): candidate_tickers = [sid]
    else:
        suffixes = [".TWO", ".TW"] if sid in ["3595", "7853", "3081"] or len(sid) == 6 else [".TW", ".TWO"]
        candidate_tickers = [f"{sid}{s}" for s in suffixes]

    is_finance_sector = sid.split('.')[0].startswith(("28", "58"))
    result = {
        "has_data": False, "latest_gm": "N/A", "latest_opm": "N/A", "annual_gm_dict": {},
        "quarterly_gm_dict": {}, "gm_3y_diff": 0.0, "annual_rev_cagr": 0.0,
        "is_long_term_growth": False, "is_q_dip_opportunity": False,
        "status_tag": "⚖️ 財報中性", "diagnosis_text": "【資料不足，無法確認】"
    }

    if is_finance_sector:
        result.update({"has_data": True, "latest_gm": "不適用(金融業)", "is_long_term_growth": True, 
                       "status_tag": "🏛️ 金融特許・獲利穩健", "diagnosis_text": "金融控股無營業毛利項目，以整體獲利為主。"})
        return result

    for tk_symbol in candidate_tickers:
        try:
            ticker = yf.Ticker(tk_symbol)
            info = ticker.info or {}
            if info.get("grossMargins"): result["latest_gm"] = round(float(info["grossMargins"]) * 100, 2)
            if info.get("operatingMargins"): result["latest_opm"] = round(float(info["operatingMargins"]) * 100, 2)

            ann_stmt = ticker.income_stmt
            if ann_stmt is not None and not ann_stmt.empty and "Gross Profit" in ann_stmt.index and "Total Revenue" in ann_stmt.index:
                ann_gms, ann_revs = {}, {}
                for col in sorted(ann_stmt.columns):
                    gp, rev = ann_stmt.loc["Gross Profit", col], ann_stmt.loc["Total Revenue", col]
                    if pd.notna(gp) and pd.notna(rev) and float(rev) > 0:
                        yr_str = str(col.year)
                        ann_gms[yr_str] = round((float(gp) / float(rev)) * 100, 2)
                        ann_revs[yr_str] = float(rev)
                if len(ann_gms) >= 2:
                    result["has_data"] = True
                    result["annual_gm_dict"] = ann_gms
                    yrs = list(ann_gms.keys())
                    result["gm_3y_diff"] = round(ann_gms[yrs[-1]] - ann_gms[yrs[0]], 2)
                    if ann_revs[yrs[0]] > 0:
                        result["annual_rev_cagr"] = round(((ann_revs[yrs[-1]] - ann_revs[yrs[0]]) / ann_revs[yrs[0]]) * 100, 2)
                    if (ann_gms[yrs[-1]] >= ann_gms[yrs[0]] or ann_gms[yrs[-1]] >= ann_gms[yrs[-2]]) and result["annual_rev_cagr"] > 0:
                        result["is_long_term_growth"] = True

            q_stmt = ticker.quarterly_income_stmt
            if q_stmt is not None and not q_stmt.empty and "Gross Profit" in q_stmt.index and "Total Revenue" in q_stmt.index:
                q_gms = {}
                for col in sorted(q_stmt.columns)[-4:]:
                    gp, rev = q_stmt.loc["Gross Profit", col], q_stmt.loc["Total Revenue", col]
                    if pd.notna(gp) and pd.notna(rev) and float(rev) > 0:
                        q_gms[f"{col.year}-Q{(col.month-1)//3 + 1}"] = round((float(gp) / float(rev)) * 100, 2)
                result["quarterly_gm_dict"] = q_gms

            if result["has_data"]:
                q_vals = list(result["quarterly_gm_dict"].values())
                q_rev_yoy = info.get("revenueGrowth", 0) or 0
                is_recent_q_dip = (q_rev_yoy < 0) or (len(q_vals) >= 2 and q_vals[-1] < q_vals[-2])
                if result["is_long_term_growth"] and not is_recent_q_dip:
                    result["status_tag"] = "🚀 長線毛利與營收雙成長"
                    result["diagnosis_text"] = f"歷年毛利率變動 {result['gm_3y_diff']:+.2f}%，多年度營收成長 {result['annual_rev_cagr']:+.1f}%。長線與單季基本面同步擴張！"
                elif result["is_long_term_growth"] and is_recent_q_dip:
                    result["is_q_dip_opportunity"] = True
                    result["status_tag"] = "💎 長線成長・單季逆風黃金坑"
                    result["diagnosis_text"] = f"雖近期單季小幅回檔，但跨年度毛利成長 {result['gm_3y_diff']:+.2f}%、年度營收趨勢正成長，具備長線保護傘！"
                else:
                    result["status_tag"] = "⚠️ 長線毛利或營收趨緩"
                    result["diagnosis_text"] = f"跨年度毛利率變動 {result['gm_3y_diff']:+.2f}%，年度營收變動 {result['annual_rev_cagr']:+.1f}%。宜嚴守技術與籌碼防線。"
                break
        except Exception:
            continue
    return result

@st.cache_data(ttl=5)
def get_realtime_order(sid):
    suffixes = [".TWO", ".TW"] if sid in ["3595", "7853", "3081"] or len(sid) == 6 else [".TW", ".TWO"]
    for suffix in suffixes:
        try:
            info = yf.Ticker(f"{sid}{suffix}").info
            if info:
                return info.get('bid') or info.get('regularMarketPrice') or 0, info.get('ask') or info.get('regularMarketPrice') or 0, info.get('bidSize') or 0, info.get('askSize') or 0
        except Exception: continue
    return 0, 0, 0, 0

def get_institutional_chips(sid, df):
    result = {
        "status": "success", "inst_status": "⚖️ 【法人籌碼溫和觀望】", "inst_card_type": "info",
        "net_buy_5d": "0 張", "net_buy_10d": "0 張", "major_force_status": "🟢 法人無大動作，目前走勢由大戶防護線撐腰。",
        "institutional_pct": "0.0%"
    }
    if df is not None and not df.empty and len(df) >= 10:
        df_temp = df.copy()
        df_temp['Price_Diff'] = df_temp['Close'].diff()
        df_temp['Net_Force_Vol'] = df_temp.apply(lambda r: r['Volume'] if r['Price_Diff'] > 0 else (-r['Volume'] if r['Price_Diff'] < 0 else 0.0), axis=1)
        net_5d = round(df_temp['Net_Force_Vol'].tail(5).sum(), 1)
        net_10d = round(df_temp['Net_Force_Vol'].tail(10).sum(), 1)
        result["net_buy_5d"] = f"+{net_5d} 張" if net_5d >= 0 else f"{net_5d} 張"
        result["net_buy_10d"] = f"+{net_10d} 張" if net_10d >= 0 else f"{net_10d} 張"
        if net_5d > 500:
            result.update({"inst_status": "🚀 【三大法人與主力強烈鎖碼】", "inst_card_type": "success", "major_force_status": "🔥 主力大戶急速拉高進貨，強烈多頭防線成立！"})
        elif net_5d < -500:
            result.update({"inst_status": "⚠️ 【法人與主力高檔調節倒貨】", "inst_card_type": "error", "major_force_status": "⚡ 主力大戶大舉提款出貨，拉高不宜盲目追進！"})
    return result

def calculate_composite_score(net_5d, volume_ratio, is_long_term_growth=False, is_q_dip=False, signal_type=""):
    if net_5d is None: net_5d = 0
    if volume_ratio is None: volume_ratio = 1.0
    chip_score = min(max((net_5d / 3000.0) * 100, 0), 100)
    if "惜售" in signal_type or "潛龍" in signal_type or "背離" in signal_type or volume_ratio < 0.7:
        vol_score = min(max((0.7 - volume_ratio) / 0.7 * 100, 0), 100)
    else:
        vol_score = min(max((volume_ratio - 1.15) / (3.0 - 1.15) * 100, 0), 100)
    base_score = (chip_score * 0.50) + (vol_score * 0.35)
    fin_bonus = 15.0 if is_long_term_growth else (10.0 if is_q_dip else 0.0)
    return round(min(base_score + fin_bonus, 100.0), 2)

def send_discord_webhook(webhook_url, embed_data):
    if not webhook_url: return False, "未填寫 Discord Webhook URL"
    try:
        response = requests.post(webhook_url, json={"embeds": [embed_data]} if isinstance(embed_data, dict) else {"content": embed_data}, timeout=5)
        if response.status_code in [200, 204]: return True, "發送成功！"
        return False, f"發送失敗，狀態碼: {response.status_code}"
    except Exception as e: return False, f"發送異常: {str(e)}"

# ==============================================================================
# 🎨 視覺與卡片渲染模組
# ==============================================================================
def custom_diagnostic_card(title, text, card_type="info"):
    theme_colors = {
        "success": {"border": "#10b981", "title_color": "#34d399"},
        "warning": {"border": "#f59e0b", "title_color": "#fbbf24"},
        "error": {"border": "#ef4444", "title_color": "#f87171"},
        "info": {"border": "#3b82f6", "title_color": "#60a5fa"}
    }
    cfg = theme_colors.get(card_type, theme_colors["info"])
    st.markdown(f"""
    <div style="background-color: #1e293b; border-left: 6px solid {cfg['border']}; border-top: 1px solid #334155; border-right: 1px solid #334155; border-bottom: 1px solid #334155; padding: 12px 16px; border-radius: 8px; margin-bottom: 10px; white-space: pre-line; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.1);">
        <h4 style="color: {cfg['title_color']}; margin: 0 0 6px 0; font-size: 19px; font-weight: 900;">{title}</h4>
        <div style="color: #e2e8f0; margin: 0; font-size: 15px; line-height: 1.6;">{text}</div>
    </div>
    """, unsafe_allow_html=True)

# ==============================================================================
# 📊 策略回測中心與連動模組
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
        st.markdown("""<div style="background: linear-gradient(145deg, #1e293b, #0f172a); border: 1px solid #334155; border-left: 5px solid #38bdf8; padding: 18px 20px; border-radius: 12px;">
            <span style="color: #38bdf8; font-size: 18px; font-weight: 900;">🏹 連續鎖碼偵測核心指南</span><br><br>
            <span style="color: #e2e8f0; font-size: 14px;">徹底消滅「單日一日遊」假突破，確認大戶分批鎖碼。建議每日開盤前檢視。</span>
            </div>""", unsafe_allow_html=True)

    with col_main:
        if os.path.exists("signal_history.csv"):
            df_history = pd.read_csv("signal_history.csv", encoding="utf-8-sig", on_bad_lines='skip')
            df_history['日期'] = pd.to_datetime(df_history['日期時間']).dt.date
            df_history['核心訊號'] = df_history['核心訊號'].apply(force_clean)
            df_daily = df_history.drop_duplicates(subset=['日期', '股票代號'], keep='last')
            all_dates = sorted(df_daily['日期'].unique(), reverse=True)
            
            t1, t2 = st.tabs(["🚀 最新盤前偵測", "⏪ 歷史時光機回測"])
            with t1:
                target_days = st.slider("🔥 連續上榜天數", 2, 5, 2, key="sl_late")
                if len(all_dates) >= target_days:
                    chk_dates = all_dates[:target_days]
                    for ticker, grp in df_daily[df_daily['日期'].isin(chk_dates)].groupby('股票代號'):
                        if len(grp) == target_days and grp['核心訊號'].nunique() == 1:
                            st.success(f"✅ {ticker} {grp['股票名稱'].iloc[0]} - {grp['核心訊號'].iloc[0]}")
            with t2:
                b_date = st.date_input("📅 基準日", value=all_dates[0] if all_dates else datetime.date.today())
                p_dates = [d for d in all_dates if d <= b_date]
                t_days_hist = st.slider("🔥 歷史連續天數", 2, 5, 2, key="sl_hist")
                if len(p_dates) >= t_days_hist:
                    chk_dates_h = p_dates[:t_days_hist]
                    for ticker, grp in df_daily[df_daily['日期'].isin(chk_dates_h)].groupby('股票代號'):
                        if len(grp) == t_days_hist and grp['核心訊號'].nunique() == 1:
                            st.success(f"✅ {ticker} {grp['股票名稱'].iloc[0]} - {grp['核心訊號'].iloc[0]}")
        else: st.warning("尚未產生回測日誌。")

    st.markdown("---")
    st.markdown("## 📈 策略多週期持股勝率模擬分析儀")
    if not os.path.exists("signal_history_backtest.csv"):
        st.warning("請確認回測引擎是否已執行完畢。")
        return 
    
    df = pd.read_csv("signal_history_backtest.csv", encoding="utf-8-sig", on_bad_lines='skip')
    df['核心訊號'] = df['核心訊號'].apply(force_clean)
    df['日期時間'] = pd.to_datetime(df['日期時間'])
    
    c1, c2 = st.columns(2)
    min_date, max_date = df['日期時間'].dt.date.min(), df['日期時間'].dt.date.max()
    with c1: sel_dates = st.date_input("🗓️ 回測區間", value=[max(min_date, max_date - datetime.timedelta(days=30)), max_date], min_value=min_date, max_value=max_date)
    with c2: sel_sigs = st.multiselect("🎯 訊號型態", options=df['核心訊號'].unique().tolist(), default=df['核心訊號'].unique().tolist())

    if len(sel_dates) == 2: df = df[(df['日期時間'].dt.date >= sel_dates[0]) & (df['日期時間'].dt.date <= sel_dates[1]) & (df['核心訊號'].isin(sel_sigs))]
    elif len(sel_dates) == 1: df = df[(df['日期時間'].dt.date == sel_dates[0]) & (df['核心訊號'].isin(sel_sigs))]
    
    if df.empty: return st.warning("⚠️ 沒有找到任何符合的回測數據。")

    reward_cols = [c for c in df.columns if "報酬率(%)" in c]
    df_plot = df[['核心訊號'] + reward_cols].copy()
    for col in reward_cols: df_plot[col] = pd.to_numeric(df_plot[col].astype(str).str.replace('%', ''), errors='coerce').fillna(0)

    fig = go.Figure()
    sig_cmap = {"🚨【強勢突破】": "#c084fc", "💎【大戶惜售】": "#34d399", "💀【出貨陷阱】": "#f87171", "🐉【深水區潛龍】": "#fb923c", "🔥【低檔底背離】": "#facc15", "⚖️ 區間溫和": "#94a3b8"}
    periods = ["T+1", "T+3", "T+5", "T+10", "T+20"]
    insights = []

    for sig, grp in df_plot.groupby('核心訊號'):
        wrs = [(len(grp[(grp[c] != 0) & (grp[c] > 0)]) / len(grp[grp[c] != 0]) * 100) if len(grp[grp[c] != 0]) > 0 else 0 for c in reward_cols]
        if max(wrs) > 0: insights.append(f"**{sig}** 在 **{periods[wrs.index(max(wrs))]}** 勝率最高（`{max(wrs):.1f}%`）")
        fig.add_trace(go.Scatter(x=periods, y=wrs, mode='lines+markers+text', name=sig, text=[f"{v:.1f}%" for v in wrs], textposition="top center", line=dict(width=3, color=sig_cmap.get(sig, "#38bdf8")), marker=dict(size=10)))
    
    fig.update_layout(height=400, title="不同訊號之多週期勝率演變交叉圖", yaxis=dict(range=[0, 110]), hovermode="x unified", legend=dict(orientation="h", y=-0.2), margin=dict(l=20, r=20, t=60, b=20), template="plotly_dark")
    st.plotly_chart(fig, use_container_width=True)

    if insights: st.success(f"🎯 **即時週期勝率指引**：{' ｜ '.join(insights[:3])}")

def run_single_scan_signal(sid, sname, webhook_url):
    df_scan = get_stock_df(sid)
    if df_scan.empty or len(df_scan) < 20: return None
    
    last, prev = df_scan.iloc[-1], df_scan.iloc[-2]
    cp = get_yahoo_web_quote_from_df(sid, df_scan)
    cur_p, prv_p = cp["current"], cp["prev_close"]
    vol_ratio = last['Volume'] / last['Vol_MA5'] if last['Vol_MA5'] > 0 else 1
    a_data = get_analysis_data(sid)
    inst_val = a_data['法人持股'] if (a_data and '法人持股' in a_data and a_data['法人持股'] != 'N/A') else 0
    
    df_t = df_scan.copy()
    df_t['Price_Diff'] = df_t['Close'].diff()
    df_t['Net_Force'] = df_t.apply(lambda r: r['Volume'] if r['Price_Diff'] > 0 else (-r['Volume'] if r['Price_Diff'] < 0 else 0), axis=1)
    n5d = round(df_t['Net_Force'].tail(5).sum(), 1)
    
    c_status = f"🚀 **主力強烈鎖碼進貨 (+{n5d}張)**" if n5d > 500 else (f"⚠️ __**主力高檔調節倒貨 ({n5d}張)**__" if n5d < -500 else "⚖️ 法人溫和觀望")
    msg, hex_c, trig = "⚖️ 區間溫和", 15158332 if cur_p >= prv_p else 3066993, False

    if vol_ratio >= 1.15:
        msg, hex_c, trig = ("💀【出貨陷阱】爆量但主力高檔倒貨！", 7368816, True) if "倒貨" in c_status else ("🚨【強勢突破】量能爆發且籌碼健康！", 16711680, True)
    elif vol_ratio < 0.7:
        if cur_p >= last['MA5'] and (last['RSI'] >= 50 or inst_val > 15):
            msg, hex_c, trig = ("💎【大戶惜售】量縮鎖碼，籌碼穩定", 3447003, True)

    try:
        ma60, ma240, v20 = last.get('MA60', 0), last.get('MA240', 0), df_scan['Volume'].rolling(20).mean().iloc[-1]
        if pd.notna(ma60) and pd.notna(ma240) and pd.notna(v20):
            if (abs(cur_p - ma60)/ma60 <= 0.05 or abs(cur_p - ma240)/ma240 <= 0.05) and (last['Volume'] < v20 * 0.4) and (last['RSI'] <= 35) and ("倒貨" not in c_status):
                if v20 > 300 and last['MACD_Hist'] >= prev['MACD_Hist'] and inst_val > 1.0:
                    msg, hex_c, trig = (f"🐉【深水區潛龍】測 {'年線(240MA)' if abs(cur_p - ma240)/ma240 <= 0.05 else '季線(60MA)'} (籌碼安全)！", 16766720, True)
    except: pass

    if len(df_scan) >= 10:
        p_min_c, p_min_rsi = df_scan.iloc[-10:-1]['Close'].min(), df_scan.iloc[-10:-1]['RSI'].min()
        if (cur_p <= p_min_c) and (last['RSI'] > p_min_rsi) and (last['RSI'] < 40):
            msg, hex_c, trig = ("🔥【低檔底背離】下跌力道竭盡，醞釀強彈！", 16744192, True)

    if trig:
        fin_trend = get_financial_margin_trend(sid)
        score = calculate_composite_score(n5d, vol_ratio, is_long_term_growth=fin_trend["is_long_term_growth"], is_q_dip=fin_trend["is_q_dip_opportunity"], signal_type=msg)
        embed = {
            "title": f"🚨 黑馬雷達警戒：{sname} ({sid})",
            "description": f"🔥 **綜合火力評分：{score} 分**\n\n**表面型態**：**`{msg}`**",
            "color": hex_c,
            "fields": [
                {"name": "💰 報價與技術", "value": f"現價：{cur_p} 元 | RSI：{round(last['RSI'], 2)} | 量比：{round(vol_ratio, 2)}x", "inline": False},
                {"name": "👥 內部籌碼與毛利", "value": f"資金流向：{c_status}\n歷年毛利：{fin_trend['status_tag']}", "inline": False}
            ]
        }
        return {"sid": sid, "sname": sname, "score": score, "current_price": cur_p, "status_msg": msg, "embed": embed}
    return None

# ==============================================================================
# 🚀 系統入口點與全局變數設定
# ==============================================================================
if 'STOCK_DICT' not in st.session_state: st.session_state['STOCK_DICT'] = load_stock_dict()
if 'INDUSTRY_DB' not in st.session_state: st.session_state['INDUSTRY_DB'] = load_industry_db()
if 'app_mode' not in st.session_state: st.session_state['app_mode'] = "🎯 個股戰情室"
if 'selected_sid' not in st.session_state: st.session_state['selected_sid'] = list(st.session_state['STOCK_DICT'].keys())[0] if st.session_state['STOCK_DICT'] else "2330"

with st.sidebar:
    st.sidebar.markdown("""<div style="background: linear-gradient(135deg, #1e3a8a, #000000); padding: 20px; border-radius: 15px; border: 1.5px solid #3b82f6; text-align: center;">
        <h1 style="color: #60a5fa; font-size: 20px; font-weight: 900; margin: 0;">🚀 戰情操控中心</h1>
        <p style="color: #94a3b8; font-size: 12px; margin-top:8px;">吳秉諺 專屬 AI 投資系統 v42.5</p></div>""", unsafe_allow_html=True)
    st.write("") 
    
    col1, col2 = st.columns(2)
    if col1.button("🎯 個股戰情", use_container_width=True, type="primary" if st.session_state['app_mode'] == "🎯 個股戰情室" else "secondary"):
        st.session_state['app_mode'] = "🎯 個股戰情室"
        st.rerun()
    if col2.button("📊 回測中心", use_container_width=True, type="primary" if st.session_state['app_mode'] == "📊 策略回測中心" else "secondary"):
        st.session_state['app_mode'] = "📊 策略回測中心"
        st.rerun()

    app_mode = st.session_state['app_mode']
    st.divider()

if app_mode == "📊 策略回測中心":
    render_backtest_dashboard()
    st.stop()

# ==============================================================================
# 🎯 個股戰情室
# ==============================================================================
current_stocks_dict = st.session_state['STOCK_DICT']
full_market_data = load_full_market() 

with st.sidebar:
    st.markdown("### 🎯 每日戰情室 (已關注)")
    options_list = list(current_stocks_dict.keys())
    try: current_idx = options_list.index(st.session_state['selected_sid'])
    except: current_idx = 0

    target_sid = st.selectbox("選擇每日觀察標的", options=options_list, index=current_idx, format_func=lambda sid: current_stocks_dict.get(sid, sid))
    st.session_state['selected_sid'] = target_sid
    st.divider()
    
    with st.expander("🔍 搜尋全市場並擴建雷達"):
        search_options = [f"{sid} ({name})" for sid, name in full_market_data.items()]
        new_stock_input = st.selectbox("請輸入代號或名稱搜尋", options=search_options)
        if st.button("➕ 加入每日戰情室", use_container_width=True) and new_stock_input:
            clean_new_sid = new_stock_input.split(" ")[0].strip().split(".")[0]
            if clean_new_sid not in current_stocks_dict:
                current_stocks_dict[clean_new_sid] = f"{clean_new_sid} ({full_market_data.get(new_stock_input.split(' ')[0].strip(), '未知標的')})"
                save_stock_dict(current_stocks_dict)
                st.session_state['STOCK_DICT'] = current_stocks_dict
                st.session_state['selected_sid'] = clean_new_sid
                st.success(f"✅ 已成功加入: {current_stocks_dict[clean_new_sid]} \n(百科請視需求手動生成)")
                time.sleep(0.8); st.rerun()
            else: st.warning("⚠️ 此標的已在清單中！")
            
    view_days = st.slider("📅 歷史數據追蹤天數", 30, 240, 90)
    st.divider()

    st.markdown("### 🏢 AI 產業百科")
    stock_info = st.session_state['INDUSTRY_DB'].get(str(target_sid).strip())
    if stock_info:
        def fmt(v): return "\n\n".join([f"🔸 {x}" for x in (v.values() if isinstance(v, dict) else v)]) if isinstance(v, (dict, list)) else str(v)
        with st.expander("🎯 個股主要業務", expanded=True): st.info(fmt(stock_info.get("company_brief", "")))
        with st.expander("📍 產業市場規模", expanded=False): st.info(fmt(stock_info.get("overview", "")))
        with st.expander("🔗 產業價值鏈", expanded=False): st.info(fmt(stock_info.get("value_chain", "")))
        with st.expander("🔗 相關競爭對手", expanded=False): st.markdown("\n".join([f"- **{peer}**" for peer in stock_info.get("competitors", [])]) or "暫無資料")
        with st.expander("📈 產業驅動因子", expanded=False): st.info(fmt(stock_info.get("drivers", "")))
        
        lu_str = stock_info.get('last_updated', '2020-01-01')
        try:
            if (datetime.date.today() - datetime.date.fromisoformat(lu_str)).days > 7: st.warning("⚠️ 資料已過期，建議更新")
            else: st.caption(f"✨ 百科更新時間：{lu_str}")
        except: st.caption(f"✨ 百科更新時間：{lu_str}")

        if stock_info.get("source_url"): st.markdown(f'<div style="text-align: right;"><a href="{stock_info["source_url"]}" target="_blank" style="color: #60a5fa; font-size: 13px;">🔍 AI 參考來源網頁 →</a></div>', unsafe_allow_html=True)
        
        if st.button("🔄 更新這檔百科", use_container_width=True):
            with st.status(f"🚀 正在重塑 {target_sid} 產業百科..."):
                success, msg = auto_update_industry_db(target_sid)
                if success: st.rerun()
                else: st.error(f"更新失敗: {msg}")
    else:
        st.warning(f"⚠️ 庫存中無 {target_sid} 的資料")
        if st.button(f"🎯 消耗額度生成百科", use_container_width=True):
            with st.status(f"🤖 正在建立全新百科..."):
                success, msg = auto_update_industry_db(target_sid)
                if success: st.rerun()
                else: st.error(f"生成失敗: {msg}")

    st.divider()
    with st.expander("🛠️ 系統後勤工具", expanded=False):
        if st.button("🔍 版本測試", use_container_width=True): st.toast("正在測試...")
        if st.button("📋 模型清單", use_container_width=True):
            try:
                st.json([m.name.replace("models/", "") for m in genai.list_models() if 'generateContent' in m.supported_generation_methods])
            except Exception as ex: st.error(f"查詢失敗: {ex}")
            
    st.markdown("**資料庫管理 (已開啟雲端雙軌同步)**")
    if st.button("🚀 執行本地與雲端智慧合併", use_container_width=True): migrate_local_to_cloud()
    
    st.download_button("📥 下載最新百科 (industry_db.json)", json.dumps(st.session_state['INDUSTRY_DB'], ensure_ascii=False, indent=4), "industry_db.json", "application/json", use_container_width=True)
    st.download_button("📥 下載最新自選股 (watchlist.json)", json.dumps({k: v for k, v in st.session_state['STOCK_DICT'].items() if "(⚡雷達)" not in str(v)}, ensure_ascii=False, indent=4), "watchlist.json", "application/json", use_container_width=True)
    if os.path.exists("signal_history.csv"):
        with open("signal_history.csv", "rb") as f: st.download_button("📥 下載策略回測日誌", f.read(), "signal_history.csv", "text/csv", use_container_width=True)
    
    uploaded_csv = st.file_uploader("上傳 CSV 覆蓋日誌", type=["csv"], label_visibility="collapsed")
    if uploaded_csv is not None:
        with open("signal_history.csv", "wb") as f: f.write(uploaded_csv.getbuffer())
        st.success("✅ 乾淨的回測日誌已成功覆蓋！")

# ==============================================================================
# 📈 主畫面數據載入與圖表渲染
# ==============================================================================
clean_sid = re.search(r'\d+', str(target_sid)).group() if re.search(r'\d+', str(target_sid)) else str(target_sid)
df = get_stock_df(clean_sid)
a_data = get_analysis_data(clean_sid)
bid_p, ask_p, bid_s, ask_s = get_realtime_order(clean_sid)

if df is not None and not df.empty:
    last, prev = df.iloc[-1], df.iloc[-2]
    clean_prices = get_yahoo_web_quote_from_df(clean_sid, df)
    current_price, prev_price = clean_prices["current"], clean_prices["prev_close"]
    
    diff = round(current_price - prev_price, 2)
    diff_pct = round((diff / prev_price) * 100, 2) if prev_price > 0 else 0
    price_color = "#ef4444" if diff > 0 else ("#10b981" if diff < 0 else "white")
    arrow = "▲" if diff > 0 else ("▼" if diff < 0 else "-")
    
    today_volume, vol_ma5 = last['Volume'], last['Vol_MA5']
    vol_ratio = (today_volume / vol_ma5) if vol_ma5 > 0 else 1
    
    try:
        calculated_support = round(df.tail(60).nlargest(3, 'Volume')['Low'].mean(), 1)
        weighted_support = calculated_support if 0.75 * current_price <= calculated_support <= 1.02 * current_price else (round(df.tail(10)['Low'].min(), 1) if 0.75 * current_price <= round(df.tail(10)['Low'].min(), 1) <= 1.02 * current_price else round(current_price * 0.95, 1))
    except: weighted_support = round(current_price * 0.95, 1)

    if vol_ratio > 1.5: vol_diag_msg = "⚡ 量能爆發"
    elif vol_ratio < 0.7:
        if current_price >= last['MA5'] and (last['RSI'] >= 50 or (a_data and a_data.get('法人持股', 0) != 'N/A' and a_data['法人持股'] > 15)):
            vol_diag_msg = "💎 大戶惜售 / 籌碼鎖定"
        else: vol_diag_msg = "🥶 人氣退潮"
    else: vol_diag_msg = "⚖️ 量能溫和"

    plot_df = df.tail(view_days)
    rsi_val = round(plot_df['RSI'].dropna().iloc[-1], 2) if not plot_df['RSI'].dropna().empty else 50.0
    inst_val = a_data.get('法人持股', 0) if a_data else 0
    
    if rsi_val > 80: color, msg = "#ef4444", f"⚠️【高檔過熱：禁止追高】"
    elif rsi_val < 40: color, msg = "#10b981", f"✅【低檔安全：留意佈局】"
    else: color, msg = "#f59e0b", f"⚖️【區間震盪：觀望趨勢】"

    display_name = current_stocks_dict.get(clean_sid, str(target_sid))

    # 🌟 第 1 層：頂部全寬戰情大看板
    st.markdown(f"""<div style="background: linear-gradient(90deg, #111827, #000000); border-left: 10px solid {color}; padding: 18px 25px; border-radius: 12px; display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 15px; margin-bottom: 15px;">
        <div style="min-width: 320px;">
            <div style="display: flex; align-items: baseline; gap: 15px; margin-bottom: 5px;">
                <h2 style="color:white; font-size: 32px; font-weight: 900; margin:0;">{display_name}</h2>
                <span style="font-size: 18px; color: {color}; font-weight: bold; background-color: rgba(255,255,255,0.05); padding: 2px 10px; border-radius: 20px;">RSI: {rsi_val}</span>
            </div>
            <p style="color:{color}; font-size: 20px; font-weight: bold; margin: 5px 0 0 0;">
                {msg} <span style="color: #475569; margin: 0 10px;">|</span> <span style="color: #e2e8f0; font-size: 16px; background-color: #1e293b; padding: 4px 12px; border-radius: 6px;">{vol_diag_msg}</span>
            </p>
        </div>
        <div style="display: flex; align-items: center; gap: 20px; flex-wrap: wrap; justify-content: flex-end;">
            <div style="text-align: right; padding-right: 20px; border-right: 2px solid #334155;">
                <p style="color: #94a3b8; font-size: 12px; margin: 0 0 4px 0;">最新報價</p>
                <div style="display: flex; align-items: baseline; gap: 10px; justify-content: flex-end;">
                    <span style="color: {price_color}; font-size: 38px; font-weight: 900; line-height: 1;">{round(current_price, 2)}</span>
                    <span style="color: {price_color}; font-size: 18px; font-weight: bold;">{arrow} {abs(diff)} ({diff_pct}%)</span>
                </div>
            </div>
            <div style="display: flex; gap: 8px;">
                <div style="background-color: #1e293b; width: 75px; padding: 8px 5px; border-radius: 8px; text-align: center;"><p style="color: #cbd5e1; font-size: 11px; margin: 0;">昨收</p><p style="color: #e2e8f0; font-size: 17px; font-weight: bold; margin: 4px 0 0 0;">{round(prev_price, 2)}</p></div>
                <div style="background-color: #1e293b; width: 75px; padding: 8px 5px; border-radius: 8px; text-align: center;"><p style="color: #38bdf8; font-size: 11px; margin: 0;">開盤</p><p style="color: white; font-size: 17px; font-weight: bold; margin: 4px 0 0 0;">{round(float(last['Open']), 2)}</p></div>
                <div style="background-color: #1e293b; width: 75px; padding: 8px 5px; border-radius: 8px; text-align: center;"><p style="color: #ef4444; font-size: 11px; margin: 0;">最高</p><p style="color: white; font-size: 17px; font-weight: bold; margin: 4px 0 0 0;">{round(float(last['High']), 2)}</p></div>
                <div style="background-color: #1e293b; width: 75px; padding: 8px 5px; border-radius: 8px; text-align: center;"><p style="color: #10b981; font-size: 11px; margin: 0;">最低</p><p style="color: white; font-size: 17px; font-weight: bold; margin: 4px 0 0 0;">{round(float(last['Low']), 2)}</p></div>
            </div>
        </div>
    </div>""", unsafe_allow_html=True)

    # 🌟 第 2 層：核心交易雙屏對齊 (左側 K線主圖 65% ＋ 右側即時盤口 35%)
    col_chart, col_telemetry = st.columns([2.6, 1.4])
    with col_chart:
        bb_upper, bb_lower = plot_df['MA20'] + (plot_df['Close'].rolling(20).std() * 2), plot_df['MA20'] - (plot_df['Close'].rolling(20).std() * 2)
        macd_g = (plot_df['DIF'] > plot_df['DEA']) & (plot_df['DIF'].shift(1) <= plot_df['DEA'].shift(1))
        macd_d = (plot_df['DIF'] < plot_df['DEA']) & (plot_df['DIF'].shift(1) >= plot_df['DEA'].shift(1))
        kd_g = (plot_df['K'] > plot_df['D']) & (plot_df['K'].shift(1) <= plot_df['D'].shift(1))
        kd_d = (plot_df['K'] < plot_df['D']) & (plot_df['K'].shift(1) >= plot_df['D'].shift(1))
        vol_b = (plot_df['Close'] > plot_df['Open']) & (plot_df['Volume'] >= plot_df['Vol_MA5'] * 1.15)
        bull_res = (kd_g & (macd_g | macd_g.shift(1, fill_value=False) | macd_g.shift(-1, fill_value=False) | (vol_b & (plot_df['MACD_Hist'] > plot_df['MACD_Hist'].shift(1))))) | (macd_g & (kd_g | kd_g.shift(1, fill_value=False) | kd_g.shift(-1, fill_value=False)))

        fig = make_subplots(rows=5, cols=1, shared_xaxes=True, vertical_spacing=0.065, row_heights=[0.38, 0.15, 0.16, 0.16, 0.15], subplot_titles=(f"📈 {display_name} K線與防線 ({weighted_support}元)", "📊 成交量", "🌊 MACD", "⚡ KD", "🎯 RSI (14)"))
        
        # Row 1
        fig.add_trace(go.Candlestick(x=plot_df.index, open=plot_df['Open'], high=plot_df['High'], low=plot_df['Low'], close=plot_df['Close'], name="K線", decreasing=dict(fillcolor='#00e676', line=dict(color='#00e676')), increasing=dict(fillcolor='#ff3b5c', line=dict(color='#ff3b5c'))), row=1, col=1)
        fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df['MA5'], name="5MA", line=dict(color='#fb923c', width=1.5)), row=1, col=1)
        fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df['MA20'], name="20MA", line=dict(color='#c084fc', width=1.8)), row=1, col=1)
        fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df['MA60'], name="60MA", line=dict(color='#2dd4bf', width=2.2)), row=1, col=1)
        fig.add_trace(go.Scatter(x=plot_df.index, y=bb_upper, name="布林上軌", showlegend=False, line=dict(color='rgba(148,163,184,0.4)', width=1, dash='dash')), row=1, col=1)
        fig.add_trace(go.Scatter(x=plot_df.index, y=bb_lower, name="布林下軌", showlegend=False, line=dict(color='rgba(148,163,184,0.4)', width=1, dash='dash'), fill='tonexty', fillcolor='rgba(148,163,184,0.04)'), row=1, col=1)
        fig.add_hline(y=weighted_support, line_dash="dash", line_color="#facc15", line_width=1.8, annotation_text=f"🛡️ 防線 {weighted_support}", annotation_font=dict(color="#facc15", size=12), row=1, col=1)
        if not plot_df[bull_res].empty:
            fig.add_trace(go.Scatter(x=plot_df[bull_res].index, y=plot_df[bull_res]['Low']*0.985, mode='markers', name="⭐共振買點", marker=dict(symbol='star', size=13, color='#facc15', line=dict(width=1))), row=1, col=1)
            for dt in plot_df[bull_res].index: fig.add_vline(x=dt, line_width=1.2, line_dash="dot", line_color="rgba(250,204,21,0.35)")

        # Row 2
        vc = ['#f59e0b' if (r['Close']>=r['Open'] and r['Volume']>=r['Vol_MA5']*1.15) else ('#ff3b5c' if r['Close']>=r['Open'] else '#00e676') for i, r in plot_df.iterrows()]
        fig.add_trace(go.Bar(x=plot_df.index, y=plot_df['Volume'], name="成交量", showlegend=False, marker_color=vc), row=2, col=1)
        fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df['Vol_MA5'], name="5日均量", showlegend=False, line=dict(color='#fef08a', width=2)), row=2, col=1)

        # Row 3
        fig.add_trace(go.Bar(x=plot_df.index, y=plot_df['MACD_Hist'], name="MACD柱", showlegend=False, marker_color=['#ff3b5c' if x>0 else '#00e676' for x in plot_df['MACD_Hist']]), row=3, col=1)
        fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df['DIF'], name="DIF", showlegend=False, line=dict(color='#38bdf8', width=1.8)), row=3, col=1)
        fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df['DEA'], name="DEA", showlegend=False, line=dict(color='#facc15', width=1.8)), row=3, col=1)
        if not plot_df[macd_g].empty: fig.add_trace(go.Scatter(x=plot_df[macd_g].index, y=plot_df[macd_g]['DIF'], mode='markers', name="MACD活叉", showlegend=False, marker=dict(symbol='triangle-up', size=12, color='#fde047', line=dict(width=1))), row=3, col=1)
        if not plot_df[macd_d].empty: fig.add_trace(go.Scatter(x=plot_df[macd_d].index, y=plot_df[macd_d]['DIF'], mode='markers', name="MACD死叉", showlegend=False, marker=dict(symbol='triangle-down', size=12, color='#06b6d4', line=dict(width=1))), row=3, col=1)

        # Row 4
        fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df['K'], name="K", showlegend=False, line=dict(color='#ffffff', width=1.8)), row=4, col=1)
        fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df['D'], name="D", showlegend=False, line=dict(color='#facc15', width=1.8)), row=4, col=1)
        fig.add_hline(y=80, line_dash="dot", line_color="rgba(239,68,68,0.5)", row=4, col=1)
        fig.add_hline(y=20, line_dash="dot", line_color="rgba(16,185,129,0.5)", row=4, col=1)
        if not plot_df[kd_g].empty: fig.add_trace(go.Scatter(x=plot_df[kd_g].index, y=plot_df[kd_g]['K'], mode='markers', name="KD活叉", showlegend=False, marker=dict(symbol='triangle-up', size=11, color='#fde047', line=dict(width=1))), row=4, col=1)
        if not plot_df[kd_d].empty: fig.add_trace(go.Scatter(x=plot_df[kd_d].index, y=plot_df[kd_d]['K'], mode='markers', name="KD死叉", showlegend=False, marker=dict(symbol='triangle-down', size=11, color='#06b6d4', line=dict(width=1))), row=4, col=1)

        # Row 5
        fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df['RSI'], name="RSI", showlegend=False, line=dict(color='#c084fc', width=2), fill='tozeroy', fillcolor='rgba(192,132,252,0.08)'), row=5, col=1)
        fig.add_hline(y=80, line_dash="dash", line_color="#ef4444", annotation_text="80 過熱", annotation_position="top right", annotation_font=dict(color="#ef4444", size=10), row=5, col=1)
        fig.add_hline(y=40, line_dash="dash", line_color="#10b981", annotation_text="40 背離低接區", annotation_position="bottom right", annotation_font=dict(color="#10b981", size=10), row=5, col=1)

        for ann in fig['layout']['annotations']: ann.update(x=0.0, xanchor='left', y=ann['y']+0.012, font=dict(size=13.5, color='#38bdf8', family='Microsoft JhengHei'))
        fig.update_yaxes(range=[-(m:=max(plot_df['DIF'].abs().max(), plot_df['MACD_Hist'].abs().max(), 1.0)*1.25), m], row=3, col=1)
        fig.update_yaxes(range=[-8, 112], row=4, col=1)
        fig.update_yaxes(range=[5, 98], row=5, col=1)
        fig.update_traces(xaxis="x5")
        fig.update_layout(height=1000, template="plotly_dark", hovermode="x", legend=dict(orientation="h", y=1.05, x=0), margin=dict(l=10, r=10, t=90, b=25))
        fig.update_xaxes(rangeslider_visible=False)
        for r in range(1, 5): fig.update_xaxes(showticklabels=False, row=r, col=1)
        fig.update_xaxes(showticklabels=True, showspikes=True, spikemode="across", spikesnap="cursor", spikecolor="#facc15", spikethickness=1.5, spikedash="dash", row=5, col=1)
        fig.update_yaxes(showspikes=True, spikecolor="#64748b", spikethickness=1, spikedash="dot")
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

    with col_telemetry:
        st.subheader("⚖️ 買賣掛單監控")
        c_b, c_a = st.columns(2)
        c_b.metric("🟢 最佳委買價", f"{round(bid_p, 2)} 元" if bid_p>0 else f"{round(current_price, 2)} 元"); c_b.caption(f"掛單: {int(bid_s)} 張" if bid_s>0 else "盤中媒合")
        c_a.metric("🔴 最佳委賣價", f"{round(ask_p, 2)} 元" if ask_p>0 else f"{round(current_price, 2)} 元"); c_a.caption(f"掛單: {int(ask_s)} 張" if ask_s>0 else "盤中媒合")
        st.progress(round((bid_s/(bid_s+ask_s)), 2) if bid_s+ask_s>0 else 0.5)
        
        st.divider(); st.subheader("📊 量能動態診斷")
        st.write(f"今日量：`{round(today_volume, 1)}` 張 | 5日量：`{round(vol_ma5, 1)}` 張 | 量比：`{round(vol_ratio*100, 1)}%`")
        custom_diagnostic_card("📊 診斷", vol_diag_msg, "info" if "溫和" in vol_diag_msg else "warning")

        st.divider(); st.subheader("🛡️ 莊家大戶防線")
        if current_price >= weighted_support: custom_diagnostic_card("🛡️ 莊家籌碼", f"🟢 防線守住 ({weighted_support} 元)", "success")
        else: custom_diagnostic_card("🛡️ 莊家籌碼", f"🔴 防線失守 ({weighted_support} 元)", "error")

        if len(df) >= 10 and (current_price <= df.iloc[-10:-1]['Close'].min()) and (last['RSI'] > df.iloc[-10:-1]['RSI'].min()) and (last['RSI'] < 40):
            custom_diagnostic_card("🔥 低檔底背離", "股價創新低但 RSI 拒絕破低，大戶低吸醞釀強彈！", "warning")

    # 🌟 第 3 層：全寬決策室與 AI 戰略官
    st.divider(); st.subheader("📊 籌碼流向、基本面毛利與實戰決策")
    c_chip, c_fin = st.columns(2)
    with c_chip:
        c_res = get_institutional_chips(clean_sid, df)
        custom_diagnostic_card(c_res["inst_status"], f"🚀 5日淨向：{c_res['net_buy_5d']}\n📊 10日淨向：{c_res['net_buy_10d']}\n💡 解讀：{c_res['major_force_status']}", c_res["inst_card_type"])
    with c_fin:
        f_trd = get_financial_margin_trend(clean_sid)
        eps_val, roe_val, pe_val = (a_data.get('EPS','N/A'), a_data.get('ROE','N/A'), a_data.get('本益比','N/A')) if a_data else ("N/A", "N/A", "N/A")
        ann_gm = " ➔ ".join([f"{k[-2:]}年:{v}%" for k,v in f_trd["annual_gm_dict"].items()]) if f_trd["annual_gm_dict"] else f"最新:{f_trd['latest_gm']}"
        custom_diagnostic_card(f"🏢 核心財報與毛利趨勢：{f_trd['status_tag']}", f"📈 歷年毛利率：{ann_gm}\n🎯 跨年成長診斷：{f_trd['diagnosis_text']}\n───────────────\n💵 EPS: {eps_val} | ⚡ PE: {pe_val} 倍 | 📊 ROE: {roe_val}", "success" if f_trd["is_long_term_growth"] else "warning")

    st.divider(); st.subheader("🎯 實戰買進決策與風報比試算")
    c_rr, c_ent = st.columns(2)
    with c_rr:
        ma20_val, ma60_val = round(float(last['MA20']), 2), round(float(last['MA60']), 2)
        bias_20 = round(((current_price - ma20_val) / ma20_val) * 100, 2) if ma20_val > 0 else 0
        ma_min, ma_max = min(last['MA5'], last['MA10'], last['MA20']), max(last['MA5'], last['MA10'], last['MA20'])
        ma_spread = round(((ma_max - ma_min) / ma_min) * 100, 2) if ma_min > 0 else 99
        up_pct = max(round(((df.tail(60)['High'].max() - current_price) / current_price) * 100, 2), 1)
        dn_pct = max(round(((current_price - weighted_support) / current_price) * 100, 2), 1)
        rr = round(up_pct / dn_pct, 2)
        
        if bias_20 > 15: rr_tag, rr_col = "⚠️ 短線正乖離過大（嚴禁追高）", "error"
        elif ma_spread <= 3 and current_price >= ma20_val: rr_tag, rr_col = "🌟 均線極致糾結突破", "success"
        elif rr >= 2 and current_price >= weighted_support: rr_tag, rr_col = f"✅ 風報比極佳（1 : {rr}）", "success"
        else: rr_tag, rr_col = f"⚖️ 區間博弈位階（1 : {rr}）", "info"
        custom_diagnostic_card(f"📐 位階與風報比：{rr_tag}", f"📏 月線乖離：{bias_20:+.2f}% | 🔗 均線糾結度：{ma_spread}%\n🎯 上檔空間：+{up_pct}% | 🛡️ 下檔風險：-{dn_pct}%", rr_col)
    with c_ent:
        custom_diagnostic_card("🪜 3-3-4 機構分批建倉與停損", f"🥇 首批試單 (5MA)：約 {round(min(current_price, last['MA5']), 2)} 元\n🥈 次批加碼 (20MA)：約 {ma20_val} 元\n🥉 第三批重倉 (防線)：約 {round(max(ma60_val, weighted_support), 2)} 元\n🛑 鐵血停損線：{round(weighted_support * 0.97, 2)} 元", "warning")

    if st.button("🧠 召喚黑馬 AI 戰略官：產出今日買賣決策報告", use_container_width=True):
        with st.spinner("🤖 正在綜合推演..."):
            try:
                ai_resp = genai.GenerativeModel("gemini-3.8-flash").generate_content(f"標的：{display_name}，現價：{current_price} 元。均線乖離率：{bias_20}%，盈虧比：1:{rr}。籌碼：{c_res['net_buy_5d']}。歷年毛利：{f_trd['status_tag']}。請以繁體中文輸出簡潔 3 點結論：1.多空位階總評 2.核心判斷依據 3.具體操作紀律。")
                st.info(ai_resp.text)
            except Exception as ex: st.error(f"AI 連線異常：{ex}")

    # 🌟 第 4 層：戰情推播控制台
    st.divider()
    st.markdown("### 📡 戰情推播控制台")
    c_tst, c_scn = st.columns(2)
    with c_tst:
        if st.button("🔗 發送 Discord 測試訊息", use_container_width=True):
            succ, m = send_discord_webhook(DEFAULT_DISCORD_WEBHOOK, {"title": "✅ 連線測試", "description": "發送成功！", "color": 3447003})
            st.success("✅ " + m) if succ else st.error("❌ " + m)
    with c_scn:
        if st.button("🔍 執行全體雷達大掃描", use_container_width=True):
            with st.spinner("🚀 深度掃描中..."):
                cands = [r for sid, sname in load_stock_dict().items() if isinstance((r := run_single_scan_signal(sid, sname, DEFAULT_DISCORD_WEBHOOK)), dict) and 'score' in r]
                if cands:
                    cands.sort(key=lambda x: x.get('score', 0), reverse=True)
                    for c in cands: log_signal_to_csv(c['sid'], c['sname'], c['current_price'], c['embed'])
                    for c in [s for s in cands if s.get('score', 0) >= 25.0][:5]:
                        send_discord_webhook(DEFAULT_DISCORD_WEBHOOK, c['embed']); time.sleep(0.5)
                    st.success("🎉 掃描完成並推播至 Discord！"); st.balloons(); time.sleep(2); st.rerun()
                else: st.info("目前無異常訊號。")
else:
    st.error("❌ 暫時無法加載技術數據，請確認標的代號。")
