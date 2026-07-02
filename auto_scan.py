# ==============================================================================
# 秉諺的黑馬雷達 - 背景自動無人值守掃描器 (auto_scan.py V34.0 - 加強篩選)
# ==============================================================================
import os
import json
import time
import datetime
import requests
import yfinance as yf
import pandas as pd

# 取得當前腳本所在的目錄，確保不論 GitHub 怎麼跑，都能找到 JSON
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DICT_FILE = os.path.join(BASE_DIR, "full_market_dict.json")

# ==============================================================================
# 🔐 【V34.0 終極安全隔離防護】
# ==============================================================================
DEFAULT_DISCORD_WEBHOOK = os.environ.get("DISCORD_WEBHOOK") or ""

def log_signal_to_csv(sid, sname, price, embed):
    log_file = "signal_history.csv"
    import datetime
    tz_tw = datetime.timezone(datetime.timedelta(hours=8))
    now_time = datetime.datetime.now(tz_tw).strftime('%Y-%m-%d %H:%M:%S')
    import os
    file_exists = os.path.isfile(log_file)
    
    try:
        pure_sname = sname
        if "(" in sname and ")" in sname:
            pure_sname = sname.split("(")[1].split(")")[0]
            
        desc = embed.get("description", "").replace("*", "").replace("`", "")
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

def load_stock_dict():
    print(f"DEBUG: 嘗試讀取檔案路徑: {DICT_FILE}")
    if os.path.exists(DICT_FILE):
        try:
            with open(DICT_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                print(f"DEBUG: 檔案載入成功，共 {len(data)} 檔")
                return data
        except Exception as e:
            print(f"DEBUG: JSON 解析錯誤: {e}")
    else:
        print(f"DEBUG: 錯誤！在 {DICT_FILE} 找不到檔案")
    return {}

def get_stock_df(sid):
    suffixes = [".TWO", ".TW"] if sid in ["3595", "7853"] or len(sid) == 6 else [".TW", ".TWO"]
    for suffix in suffixes:
        try:
            ticker = yf.Ticker(f"{sid}{suffix}")
            df = ticker.history(period="2y", auto_adjust=True, timeout=2.0)
            if df is not None and not df.empty and len(df) > 20:
                df = df.copy()
                if isinstance(df.columns, pd.MultiIndex): 
                    df.columns = df.columns.get_level_values(0)
                df = df.dropna(subset=['Close'])
                df = df[(df['Volume'] > 0) & (df['Volume'].notna())]
                df['Volume'] = df['Volume'] / 1000.0
                try:
                    f_info = ticker.fast_info
                    if f_info:
                        today_idx = df.index[-1]
                        df.loc[today_idx, 'Close'] = float(f_info['last_price'])
                        df.loc[today_idx, 'High'] = float(f_info['day_high'])
                        df.loc[today_idx, 'Low'] = float(f_info['day_low'])
                        df.loc[today_idx, 'Open'] = float(f_info['open'])
                        df.loc[today_idx, 'Volume'] = f_info['last_volume'] / 1000.0
                except Exception as ex:
                    print(f"實時快閃修正失敗: {ex}")
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
                rsv = 100 * ((df['Close'] - low_9) / denom_kd)
                df['K'] = rsv.ewm(com=2, adjust=False).mean()
                df['D'] = df['K'].ewm(com=2, adjust=False).mean()
                delta = df['Close'].diff()
                gain = (delta.where(delta > 0, 0)).rolling(14).mean()
                loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
                rs = gain / loss.replace(0, 0.00001)
                df['RSI'] = 100 - (100 / (1 + rs))
                return df
        except Exception as e:
            print(f"抓取 {sid}{suffix} K線失敗或逾時: {e}")
            continue
    return pd.DataFrame()

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
        except: continue
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

def get_analysis_data(sid):
    suffixes = [".TWO", ".TW"] if sid in ["3595", "7853"] or len(sid) == 6 else [".TW", ".TWO"]
    for suffix in suffixes:
        try:
            ticker = yf.Ticker(f"{sid}{suffix}")
            info = ticker.info
            if info:
                return {
                    "EPS": info.get("trailingEps", "N/A"),
                    "營收成長率": info.get('revenueGrowth', 0),
                    "負債比": info.get('debtToEquity', 0),
                    "法人持股": (info.get("heldPercentInstitutions", 0) or 0) * 100
                }
        except: continue
    return None

def get_institutional_chips(df):
    status = "⚖️ 法人溫和觀望"
    if df is not None and not df.empty and len(df) >= 10:
        df_temp = df.copy()
        df_temp['Price_Diff'] = df_temp['Close'].diff()
        df_temp['Net_Force_Vol'] = df_temp.apply(
            lambda r: r['Volume'] if r['Price_Diff'] > 0 else (-r['Volume'] if r['Price_Diff'] < 0 else 0.0), axis=1
        )
        net_5d = round(df_temp['Net_Force_Vol'].tail(5).sum(), 1)
        if net_5d > 500: status = f"🚀 **主力強烈鎖碼進貨 (+{net_5d}張)**"
        elif net_5d < -500: status = f"⚠️ __**主力高檔調節倒貨 ({net_5d}張)**__"
    return status

def send_discord_webhook(webhook_url, embed_data):
    try:
        payload = {"embeds": [embed_data]}
        response = requests.post(webhook_url, json=payload, timeout=5)
        return response.status_code in [200, 204]
    except Exception as e:
        print(f"發送 Discord 失敗: {e}")
        return False

def scan_and_notify(sid, sname, webhook_url, is_full_market=False):
    df_scan = get_stock_df(sid)
    if df_scan.empty or len(df_scan) < 20: return False
    last, prev = df_scan.iloc[-1], df_scan.iloc[-2]
    
    if is_full_market:
        try:
            vol_ma20 = df_scan['Volume'].rolling(20).mean().iloc[-1]
            if pd.isna(vol_ma20) or vol_ma20 < 800: return False
            ma20, ma60, ma240 = last.get('MA20', 0), last.get('MA60', 0), last.get('MA240', 0)
            if not (float(last['Close']) > ma20 > ma60 > ma240): return False
            if last.get('MACD_Hist', 0) < 0: return False
        except: pass

    clean_prices = get_yahoo_web_quote_from_df(sid, df_scan)
    current_price, prev_price = clean_prices["current"], clean_prices["prev_close"]
    vol_ratio = last['Volume'] / last['Vol_MA5'] if last['Vol_MA5'] > 0 else 1
    chip_flow_status = get_institutional_chips(df_scan)
    
    signals_triggered = False
    status_msg = "⚖️ 區間溫和"
    color_hex = 15158332 if (current_price - prev_price) >= 0 else 3066993

    if vol_ratio >= 1.15:
        signals_triggered = True
        status_msg = "💀【出貨陷阱】" if "倒貨" in chip_flow_status else "🚨【強勢突破】"
        color_hex = 7368816 if "倒貨" in chip_flow_status else 16711680

    if signals_triggered:
        embed = {"title": f"🚨 {sname} ({sid})", "description": status_msg, "color": color_hex}
        send_discord_webhook(webhook_url, embed)
        log_signal_to_csv(sid, sname, current_price, embed)
        return True
    return False

def run_all_scan():
    print(f"[{datetime.datetime.now()}] 開始執行自動掃描...")
    stock_dict = load_stock_dict()
    for sid, sname in stock_dict.items():
        print(f"DEBUG: 正在檢查 {sid} {sname}")
        scan_and_notify(sid, sname, DEFAULT_DISCORD_WEBHOOK, is_full_market=True)
    print("掃描結束")

if __name__ == "__main__":
    print("DEBUG: 程式已啟動，準備進入 run_all_scan...") 
    try:
        run_all_scan()
        print("DEBUG: run_all_scan 執行結束。")
    except Exception as e:
        print(f"DEBUG: 發生嚴重錯誤: {e}")
# 執行全體自選股掃描
#def run_all_scan():
 #   print(f"[{datetime.datetime.now()}] 開始執行背景自動掃描...")
 #   stock_dict = load_stock_dict()
    
 #   is_full_market = len(stock_dict) > 500
 #   if is_full_market:
  #      print(f"🛡️ 偵測到全市場掃描 ({len(stock_dict)} 檔)，已自動啟動「高壓前置濾網」！")
        
    # 💥 新增：準備一個空籃子，用來裝今天的菁英
#    elite_dict = {}
        
#    for sid, sname in stock_dict.items():
 #       print(f"DEBUG: 正在檢查 {sid} {sname}")
#        try:
 #           # 💥 接收回傳值，如果是菁英就裝進籃子裡
 #           is_elite = scan_and_notify(sid, sname, DEFAULT_DISCORD_WEBHOOK, is_full_market)
 #           if is_elite:
  #              elite_dict[sid] = sname
  #              
   #         time.sleep(1) # 避開 Yahoo API 頻率限制
    #    except Exception as e:
    #        print(f"掃描 {sid} 發生錯誤: {e}")
            
    # 💥 新增：掃描結束後，將今天的菁英名單「完全覆寫」到專屬檔案中
  #  if is_full_market:
   #     try:
    #        with open("radar_elite.json", "w", encoding="utf-8") as f:
     #           json.dump(elite_dict, f, ensure_ascii=False, indent=4)
     #       print(f"📝 今日菁英名單已動態更新至 radar_elite.json (共 {len(elite_dict)} 檔)")
     #   except Exception as e:
      #      print(f"寫入 radar_elite.json 失敗: {e}")
            
#    print(f"[{datetime.datetime.now()}] 全體掃描結束。")
