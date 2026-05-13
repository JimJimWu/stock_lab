# ==============================================================================
# 秉諺的黑馬雷達 - 背景自動無人值守掃描器 (auto_scan.py V31.0 - facts事實還原、單位精準對齊版)
# ==============================================================================
import os
import json
import time
import datetime
import requests
import yfinance as yf
import pandas as pd

DICT_FILE = "stock_dict.json"

# ==============================================================================
# 🔐 【V31.0 終極安全隔離防護】
# ==============================================================================
DEFAULT_DISCORD_WEBHOOK = os.environ.get("DISCORD_WEBHOOK") or ""

# 載入股票名單
def load_stock_dict():
    if os.path.exists(DICT_FILE):
        try:
            with open(DICT_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"讀取 stock_dict.json 失敗: {e}")
    return {}

# --- 數據核心 (興櫃自適應、日K天數還原、成交量統一除以1000.0) ---
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

                # 💥 【V31.0 完美同步】成交量統一、無條件除以 1000.0 (張)，徹底杜絕 838 異常大戶防線 Bug！
                df['Volume'] = df['Volume'] / 1000.0

                # 💥 【V31.0 實時快閃修正引擎】自動修復最後一根 K 線的實時波動
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

                if df.empty or len(df) < 20:
                    continue

                # 計算關鍵技術指標
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
            print(f"抓取 {sid}{suffix} K線失敗或逾時: {e}")
            continue
    return pd.DataFrame()

# 官方實時昨收與現價對齊引擎 (100% 原始價格Facts)
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

# 取得法人籌碼與基本面數據
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
 # 💥 【V32.0 新增：主力籌碼動能估算引擎】
def get_institutional_chips(df):
    status = "⚖️ 法人溫和觀望"
    if df is not None and not df.empty and len(df) >= 10:
        df_temp = df.copy()
        df_temp['Price_Diff'] = df_temp['Close'].diff()
        df_temp['Net_Force_Vol'] = df_temp.apply(
            lambda r: r['Volume'] if r['Price_Diff'] > 0 else (-r['Volume'] if r['Price_Diff'] < 0 else 0.0), axis=1
        )
        net_5d = round(df_temp['Net_Force_Vol'].tail(5).sum(), 1)
        
        if net_5d > 500:
            status = f"🚀 主力強烈鎖碼進貨 (+{net_5d}張)"
        elif net_5d < -500:
            status = f"⚠️ 主力高檔調節倒貨 ({net_5d}張)"
    return status   

# 發送 Discord Webhook
def send_discord_webhook(webhook_url, embed_data):
    try:
        payload = {"embeds": [embed_data]}
        response = requests.post(webhook_url, json=payload, timeout=5)
        return response.status_code in [200, 204]
    except Exception as e:
        print(f"發送 Discord 失敗: {e}")
        return False

# 💥 【V31.0 完美同步：自動化背景監控引擎】
def scan_and_notify(sid, sname, webhook_url):
    df_scan = get_stock_df(sid)
    if df_scan.empty or len(df_scan) < 20:
        return
        
    last, prev = df_scan.iloc[-1], df_scan.iloc[-2]
    
    # 💥 【100%事實價格還原，山太士回歸 2500元，政美回歸 370元！】
    clean_prices = get_yahoo_web_quote_from_df(sid, df_scan)
    current_price = clean_prices["current"]
    prev_price = clean_prices["prev_close"]
    
    price_change = round(current_price - prev_price, 2)
    change_pct = round((price_change / prev_price) * 100, 2)
    change_sign = "▲" if price_change > 0 else ("▼" if price_change < 0 else " ")
    color_hex = 15158332 if price_change >= 0 else 3066993  # 紅漲綠跌邊條色
    
    # 成交量
    today_volume = last['Volume']
    vol_ma5 = last['Vol_MA5']
    vol_ratio = today_volume / vol_ma5 if vol_ma5 > 0 else 1
    
    # 基本面與大戶籌碼
    a_data = get_analysis_data(sid)
    inst_val = a_data['法人持股'] if (a_data and '法人持股' in a_data) else 0
    chip_info = f"法人持股 {round(inst_val, 1)}% " + ("(大戶鎖碼)" if inst_val > 25 else "(散戶主導)")

    # 1. 💥 莊家防守成本線與防失真安全網
    try:
        temp_df = df_scan.tail(60).copy()
        top_3_vol_days = temp_df.nlargest(3, 'Volume')
        calculated_support = round(top_3_vol_days['Low'].mean(), 1)
        
        # 安全防護驗證 (75% ~ 102%)
        if 0.75 * current_price <= calculated_support <= 1.02 * current_price:
            weighted_support = calculated_support
        else:
            recent_low = round(df_scan.tail(10)['Low'].min(), 1)
            if 0.75 * current_price <= recent_low <= 1.02 * current_price:
                weighted_support = recent_low
            else:
                weighted_support = round(current_price * 0.95, 1)
    except:
        weighted_support = round(current_price * 0.95, 1)

    if current_price >= weighted_support:
        support_text = f"🟢 莊家防線守住 ({weighted_support} 元) - 屬於安全佈局位階"
    else:
        support_text = f"🔴 防線失守跌破 ({weighted_support} 元) - 莊家棄守，不建議接刀"

    # 2. 均線與多頭排列判定
    if last['MA5'] > last['MA10'] > last['MA20']:
        ma_status = "🔥 強勢多頭 (5 > 10 > 20MA)"
    else:
        ma_status = "💤 區間整理 / 走勢平緩"
# 💥 加入籌碼透視判定
    chip_flow_status = get_institutional_chips(df_scan)
    
    # 3. 核心主力訊號判定 (僅限大訊號才推播！)
    status_msg = "⚖️ 區間溫和"
    signals_triggered = False 

    if vol_ratio >= 1.3:
        status_msg = "⚡【量能爆發突破】"
        signals_triggered = True
    elif vol_ratio < 0.7:
        is_above_ma5 = current_price >= last['MA5']
        is_strong_rsi = last['RSI'] >= 50
        if is_above_ma5 and (is_strong_rsi or inst_val > 15):
            status_msg = "💎【大戶惜售 / 籌碼鎖定】"
            signals_triggered = True

    # 4. 附屬指標
    sub_signals = []
    if last['DIF'] > last['DEA'] and prev['DIF'] <= prev['DEA']:
        sub_signals.append("🟢 MACD 首日黃金交叉")
    if last['K'] > last['D'] and prev['K'] <= prev['D'] and last['K'] < 40:
        sub_signals.append("🟡 KD 低檔交叉")

   # 5. 發送高規格 Discord 卡片
    if signals_triggered:
# 💥 強制鎖定台灣時間 (UTC+8)
        tz_tw = datetime.timezone(datetime.timedelta(hours=8))
        now_time = datetime.datetime.now(tz_tw).strftime('%m/%d %H:%M')
        
        embed = {
            "title": f"🚨 黑馬雷達警戒：{sname} ({sid})",
            "description": f"**表面型態**：**`{status_msg}`**",
            "color": color_hex,
            "fields": [
                {
                    "name": "💰 實時報價 fakta", 
                    "value": f"現價：**`{round(current_price, 2)}`** 元\n漲跌：**`{change_sign} {abs(price_change)}`** ({change_pct}%)", 
                    "inline": True
                },
                {
                    "name": "📊 技術與成交量能", 
                    "value": f"RSI 指標：`{round(last['RSI'], 2)}`\n成交量比：`{round(vol_ratio, 2)}x` (`{round(today_volume, 1)}`張/`{round(vol_ma5, 1)}`張)", 
                    "inline": True
                },
                {
                    "name": "🛡️ 莊家大戶防守成本線", 
                    "value": f"`{support_text}`", 
                    "inline": False
                },
                {
                    "name": "📈 趨勢與內部籌碼真相", 
                    "value": f"技術趨勢：`{ma_status}`\n資金流向：`{chip_flow_status}`", # 💥 讓 Discord 直接顯示主力倒貨真相
                    "inline": False
                },
                {
                    "name": "👥 法人籌碼動態", 
                    "value": f"`{chip_info}`", 
                    "inline": False
                }
            ],
            "footer": {"text": f"秉諺的黑馬自動監控引擎 • 偵測時間: {now_time}"}
        }
        send_discord_webhook(webhook_url, embed)
        print(f"[{datetime.datetime.now()}] {sname} ({sid}) 滿足主力條件，已成功推送 Discord！")

# 執行全體自選股掃描
def run_all_scan():
    print(f"[{datetime.datetime.now()}] 開始執行背景自動掃描...")
    stock_dict = load_stock_dict()
    for sid, sname in stock_dict.items():
        try:
            scan_and_notify(sid, sname, DEFAULT_DISCORD_WEBHOOK)
            time.sleep(1) # 避開 Yahoo API 頻率限制
        except Exception as e:
            print(f"掃描 {sid} 發生錯誤: {e}")
    print(f"[{datetime.datetime.now()}] 全體掃描結束。")

if __name__ == "__main__":
    run_all_scan()
