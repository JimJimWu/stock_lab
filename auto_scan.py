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
    tz_tw = datetime.timezone(datetime.timedelta(hours=8))
    now_time = datetime.datetime.now(tz_tw).strftime('%Y-%m-%d %H:%M:%S')
    file_exists = os.path.isfile(log_file)
    
    try:
        # 名稱淨化邏輯
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

# 載入股票名單
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

                # 💥 【V31.0 完美同步】成交量統一、無條件除以 1000.0 (張)
                df['Volume'] = df['Volume'] / 1000.0

                # 💥 【V31.0 實時快閃修正引擎】
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
                df['MA60'] = df['Close'].rolling(60).mean()   # 💥 潛龍雷達專屬：季線
                df['MA240'] = df['Close'].rolling(240).mean() # 💥 潛龍雷達專屬：年線
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

# 💥 【V32.0 新增：主力籌碼動能估算引擎 - 視覺強化版】
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
            status = f"🚀 **主力強烈鎖碼進貨 (+{net_5d}張)**"      
        elif net_5d < -500:
            status = f"⚠️ __**主力高檔調節倒貨 ({net_5d}張)**__" 
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
# 💥 【V34.1 新增：綜合爆發力評分引擎 (籌碼 60% / 量能 40%)】
def calculate_composite_score(net_5d, volume_ratio):
    # 防呆機制：若有缺漏值則設為保守預設值
    if net_5d is None: net_5d = 0
    if volume_ratio is None: volume_ratio = 1.0

    chip_score = min(max((net_5d / 3000.0) * 100, 0), 100)
    vol_score = min(max((volume_ratio - 1.15) / (3.0 - 1.15) * 100, 0), 100)
    total_score = (chip_score * 0.6) + (vol_score * 0.4)
    return round(total_score, 2)
# 💥 【V31.0 完美同步：自動化背景監控引擎】(參數新增 is_full_market)
def scan_and_notify(sid, sname, webhook_url, is_full_market=False):
    df_scan = get_stock_df(sid)
    if df_scan.empty or len(df_scan) < 20:
        return False
        
    last, prev = df_scan.iloc[-1], df_scan.iloc[-2]
    
    # ==========================================================================
    # 🛡️ 【全母體專屬：頂尖 5% 菁英極致濾網】
    # ==========================================================================
    if is_full_market:
        try:
            # 1. 絕對流動性極致：20日均量必須大於 800 張 (放寬標準)
            vol_ma20 = df_scan['Volume'].rolling(20).mean().iloc[-1]
            if pd.isna(vol_ma20) or vol_ma20 < 800: 
                return False
                
            # 2. 均線與 MACD 動能共振 (完美多頭排列)
            ma20 = last.get('MA20', 0)
            ma60 = last.get('MA60', 0)
            ma240 = last.get('MA240', 0)
            current_price_fast = float(last['Close'])
            macd_hist = last.get('MACD_Hist', 0)
            
            if pd.notna(ma20) and pd.notna(ma60) and pd.notna(ma240) and ma240 > 0:
                if not (current_price_fast > ma20 > ma60 > ma240):
                    return False
                if pd.notna(macd_hist) and macd_hist < 0:
                    return False
                    
            # 3. 籌碼與基本面雙頂標
            a_data = get_analysis_data(sid)
            inst_val = a_data['法人持股'] if (a_data and '法人持股' in a_data) else 0
            eps_val = a_data['EPS'] if (a_data and 'EPS' in a_data) else "N/A"
            rev_growth = a_data['營收成長率'] if (a_data and '營收成長率' in a_data) else "N/A"
            
            if inst_val < 5.0: # 放寬法人持股標準
                return False
            if eps_val == "N/A" or float(eps_val) <= 0:
                return False
            if rev_growth == "N/A" or float(rev_growth) <= 0:
                return False
                
        except Exception as e:
            pass # 若運算錯誤則放行，交由後方原本邏輯處理
    # ==========================================================================
    
    # 💥 【100%事實價格還原】
    clean_prices = get_yahoo_web_quote_from_df(sid, df_scan)
    current_price = clean_prices["current"]
    prev_price = clean_prices["prev_close"]
    
    price_change = round(current_price - prev_price, 2)
    change_pct = round((price_change / prev_price) * 100, 2)
    change_sign = "▲" if price_change > 0 else ("▼" if price_change < 0 else " ")
    color_hex = 15158332 if price_change >= 0 else 3066993  # 預設紅漲綠跌邊條色
    
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
    
    # 3. 核心主力訊號判定 (視覺動態覆寫)
    status_msg = "⚖️ 區間溫和"
    signals_triggered = False 

    if vol_ratio >= 1.15: # 放寬的爆量門檻
        if "倒貨" in chip_flow_status:
            status_msg = "💀【出貨陷阱】爆量但主力高檔倒貨！"
            color_hex = 7368816 # 黯淡灰
            signals_triggered = True
        else:
            status_msg = "🚨【強勢突破】量能爆發且籌碼健康！"
            color_hex = 16711680 # 警示鮮紅
            signals_triggered = True
            
    elif vol_ratio < 0.7:
        is_above_ma5 = current_price >= last['MA5']
        is_strong_rsi = last['RSI'] >= 50
        if is_above_ma5 and (is_strong_rsi or inst_val > 15):
            status_msg = "💎【大戶惜售】量縮鎖碼，籌碼穩定"
            color_hex = 3447003 # 科技藍
            signals_triggered = True

    # ==============================================================================
    # 🐉 3.5 新增策略：深水區潛龍雷達 (實戰嚴苛版 + 籌碼防護罩)
    # ==============================================================================
    try:
        ma60 = last.get('MA60', 0)
        ma240 = last.get('MA240', 0)
        vol_ma20 = df_scan['Volume'].rolling(20).mean().iloc[-1]
        latest_rsi = last['RSI']
        
        if pd.notna(ma60) and pd.notna(ma240) and pd.notna(vol_ma20):
            SUPPORT_TOLERANCE = 0.05
            VOLUME_RATIO = 0.40
            RSI_THRESHOLD = 35
            
            is_near_ma60 = abs(current_price - ma60) / ma60 <= SUPPORT_TOLERANCE
            is_near_ma240 = abs(current_price - ma240) / ma240 <= SUPPORT_TOLERANCE
            support_test = is_near_ma60 or is_near_ma240
            
            is_volume_dead = today_volume < (vol_ma20 * VOLUME_RATIO)
            is_rsi_bottom = latest_rsi <= RSI_THRESHOLD
            is_chip_safe = "倒貨" not in chip_flow_status

            # 🔐 【放寬的高階限制條件】
            is_liquid = vol_ma20 > 300 
            is_macd_improving = last['MACD_Hist'] >= prev['MACD_Hist']
            is_inst_backed = inst_val > 1.0 
            
            if support_test and is_volume_dead and is_rsi_bottom and is_chip_safe and is_liquid and is_macd_improving and is_inst_backed:
                support_type = "年線(240MA)" if is_near_ma240 else "季線(60MA)"
                status_msg = f"🐉【深水區潛龍】測 {support_type} (籌碼安全)！"
                color_hex = 16766720 # 耀眼金
                signals_triggered = True
                
            elif support_test and is_volume_dead and is_rsi_bottom and not is_chip_safe:
                print(f"🛑 [防呆攔截] {sname} ({sid}) 技術面達標，但主力高檔倒貨中，已取消推播！")
    except Exception as e:
        pass

    # 4. 附屬指標
    sub_signals = []
    if last['DIF'] > last['DEA'] and prev['DIF'] <= prev['DEA']:
        sub_signals.append("🟢 MACD 首日黃金交叉")
    if last['K'] > last['D'] and prev['K'] <= prev['D'] and last['K'] < 40:
        sub_signals.append("🟡 KD 低檔交叉")

    # 5. 💥 發送高規格 Discord 卡片 (豪華完整版回歸)
    if signals_triggered:
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
                    "value": f"技術趨勢：`{ma_status}`\n資金流向：{chip_flow_status}", 
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
            # === 請在 scan_and_notify 內部，準備發送 Discord 的地方進行修改 ===

    # 1. 呼叫上方的新引擎計算分數 (請確保您的程式碼中有 net_5d 與 volume_ratio 變數)
    score = calculate_composite_score(net_5d, volume_ratio)

    # 2. 將分數與超連結加入敘述的最上方
    alert_description = f"# 🔥 綜合火力評分：{score} 分\n\n"
    alert_description += f"🔗 [點擊前往 Yahoo 股市查看 {sname} K線](https://tw.stock.yahoo.com/quote/{sid})\n\n"
    alert_description += "🎯 **核心主力訊號觸發！**\n"

    # 3. 組合 Embed 字典 (這裡保留您原本設定顏色與欄位的邏輯)
    embed_data = {
        "title": f"🚨 黑馬雷達：{sname} ({sid})",
        "description": alert_description,
        "color": alert_color, # 延續您的紅灰判定
        "fields": [
            # ... 保留您原本的 fields 設定 ...
        ]
    }

    # 🚨【關鍵修改】不要在這裡推播！將成功過關的資料與分數「回傳」給外層
    return {
        "sid": sid,
        "sname": sname,
        "score": score,
        "embed": embed_data
    }
        #send_discord_webhook(webhook_url, embed)
        #print(f"[{datetime.datetime.now()}] {sname} ({sid}) 滿足主力條件，已成功推送 Discord！")

        # 💥 自動化推播同步記錄至 CSV
        log_signal_to_csv(sid, sname, current_price, embed)
        return True
        
    return False 

# 執行全體自選股/全市場掃描
def run_all_scan():
    print(f"[{datetime.datetime.now()}] 開始執行背景自動掃描...")
    stock_dict = load_stock_dict()
    
    if not stock_dict:
        print("名單為空，停止掃描。")
        return

    is_full_market = len(stock_dict) > 500
    daily_candidates = []  # 建立一個空籃子，用來收集所有過關的股票

    # 第一階段：全體地毯式掃描，只收集不推播
    for sid, sname in stock_dict.items():
        print(f"掃描中: {sid} {sname}...")
        try:
            # 取得掃描結果 (若過關會拿到包含 score 的字典，若被淘汰則拿回 False/None)
            result = scan_and_notify(sid, sname, DEFAULT_DISCORD_WEBHOOK, is_full_market)
            
            if isinstance(result, dict):
                daily_candidates.append(result)
                print(f"✅ {sname} 過關！分數：{result['score']}")
                
            time.sleep(1) # 維持 API 禮貌性延遲
        except Exception as e:
            print(f"掃描 {sid} 發生錯誤: {e}")

    # 第二階段：擇優排序與 Top 10 推播截斷
    if daily_candidates:
        # 依照 score 由高到低排序
        daily_candidates.sort(key=lambda x: x['score'], reverse=True)
        
        # 擷取火力最強的前 10 名
        top_10 = daily_candidates[:10]
        print(f"\n🏆 掃描完畢！共 {len(daily_candidates)} 檔觸發，準備推播火力最強的 Top {len(top_10)}...")

        # 真正執行 Discord 推播
        for stock in top_10:
            send_discord_webhook(DEFAULT_DISCORD_WEBHOOK, stock['embed'])
            # 若您要記錄至 CSV，可在此呼叫 log_signal_to_csv (帶入正確的價格變數)
            time.sleep(1)
            
        print("✅ 今日精華推播任務完成！")
    else:
        print("今日盤勢無任何標的符合嚴格條件。")
