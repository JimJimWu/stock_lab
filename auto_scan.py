# ==============================================================================
# 秉諺的黑馬雷達 - 背景自動無人值守掃描器 (auto_scan.py V37.0 - 大盤自適應雙軌分流版)
# ==============================================================================
import os
import json
import time
import datetime
import requests
import yfinance as yf
import pandas as pd

# 取得當前腳本所在的目錄
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DICT_FILE = os.path.join(BASE_DIR, "full_market_dict.json")

# ==============================================================================
# 🔐 【終極安全隔離防護】
# ==============================================================================
DEFAULT_DISCORD_WEBHOOK = os.environ.get("DISCORD_WEBHOOK") or ""

# 記憶體快取：避免同一輪掃描重複抓取相同股票的財報
_FIN_TREND_CACHE = {}

def log_signal_to_csv(sid, sname, price, embed):
    log_file = "signal_history.csv"
    tz_tw = datetime.timezone(datetime.timedelta(hours=8))
    now_time = datetime.datetime.now(tz_tw).strftime('%Y-%m-%d %H:%M:%S')
    file_exists = os.path.isfile(log_file)
    
    try:
        pure_sname = sname
        if "(" in sname and ")" in sname:
            pure_sname = sname.split("(")[1].split(")")[0]
        
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

# ==============================================================================
# 🧭 【新增】大盤位階自適應導航引擎 (^TWII 三態判定)
# ==============================================================================
def get_market_regime():
    default_regime = {
        "mode": "BULL",
        "label": "🟢 多頭順風期 (順勢進攻 + 季線潛龍雙軌模式)",
        "allow_breakout": True,
        "allow_bottom_fish": True,
        "taiex_close": 0.0,
        "taiex_pct": 0.0
    }
    try:
        twii = yf.download("^TWII", period="6mo", progress=False)
        if twii is None or twii.empty or len(twii) < 60:
            return default_regime

        if isinstance(twii.columns, pd.MultiIndex):
            twii.columns = twii.columns.get_level_values(0)

        closes = twii["Close"].dropna()
        cur_close = float(closes.iloc[-1])
        prev_close = float(closes.iloc[-2])
        diff_pct = round(((cur_close - prev_close) / prev_close) * 100, 2)
        ma20 = float(closes.iloc[-20:].mean())
        ma60 = float(closes.iloc[-60:].mean())

        # 1. 極端警戒期：跌破季線，或跌破月線且單日重挫 <= -1.8%
        if cur_close < ma60 or (cur_close < ma20 and diff_pct <= -1.8) or diff_pct <= -2.0:
            return {
                "mode": "CRASH",
                "label": f"🔴 極端警戒/重挫撈底期 (大盤 {cur_close:,.0f} 點, {diff_pct}% | 暫停突破追價，全力掃描深水潛龍與底背離)",
                "allow_breakout": False,
                "allow_bottom_fish": True,
                "taiex_close": cur_close,
                "taiex_pct": diff_pct
            }
        # 2. 震盪洗盤期：跌破月線但守住季線，或單日跌幅介於 -1.2% ~ -2.0%
        elif cur_close < ma20 or diff_pct <= -1.2:
            return {
                "mode": "PULLBACK",
                "label": f"🟡 震盪洗盤期 (大盤 {cur_close:,.0f} 點, {diff_pct}% | 收緊突破標準，主動開啟季線撈底通道)",
                "allow_breakout": True,
                "allow_bottom_fish": True,
                "taiex_close": cur_close,
                "taiex_pct": diff_pct
            }
        # 3. 多頭順風期：站穩月線與季線之上
        else:
            return {
                "mode": "BULL",
                "label": f"🟢 多頭順風期 (大盤 {cur_close:,.0f} 點, {diff_pct}% | 順勢突破與低檔鎖碼雙軌全開)",
                "allow_breakout": True,
                "allow_bottom_fish": True,
                "taiex_close": cur_close,
                "taiex_pct": diff_pct
            }
    except Exception as e:
        print(f"⚠️ 大盤指數偵測異常，採用預設雙軌模式: {e}")
        return default_regime

def get_stock_df(sid):
    try:
        ticker = yf.Ticker(sid)
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
                if f_info is not None:
                    today_idx = df.index[-1]
                    last_p = f_info.get('last_price')
                    day_h = f_info.get('day_high')
                    day_l = f_info.get('day_low')
                    open_p = f_info.get('open')
                    last_v = f_info.get('last_volume')

                    if last_p is not None and float(last_p) > 0:
                        df.loc[today_idx, 'Close'] = float(last_p)
                    if day_h is not None and float(day_h) > 0:
                        df.loc[today_idx, 'High'] = float(day_h)
                    if day_l is not None and float(day_l) > 0:
                        df.loc[today_idx, 'Low'] = float(day_l)
                    if open_p is not None and float(open_p) > 0:
                        df.loc[today_idx, 'Open'] = float(open_p)
                    if last_v is not None and float(last_v) > 0:
                        df.loc[today_idx, 'Volume'] = float(last_v) / 1000.0
            except Exception:
                pass

            if df.empty or len(df) < 20:
                return pd.DataFrame()

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
        print(f"抓取 {sid} K線失敗或逾時: {e}")
    return pd.DataFrame()

def get_yahoo_web_quote_from_df(sid, df):
    quote = {"current": 0.0, "prev_close": 0.0, "open": 0.0, "high": 0.0, "low": 0.0, "volume_txt": "0.0"}
    try:
        ticker = yf.Ticker(sid)
        info = ticker.info
        if info:
            p_prev = info.get("regularMarketPreviousClose") or info.get("previousClose")
            if p_prev and p_prev > 0:
                quote["prev_close"] = float(p_prev)
    except Exception:
        pass
    
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
    try:
        ticker = yf.Ticker(sid)
        info = ticker.info
        if info:
            return {
                "EPS": info.get("trailingEps", "N/A"),
                "營收成長率": info.get('revenueGrowth', 0),
                "負債比": info.get('debtToEquity', 0),
                "法人持股": (info.get("heldPercentInstitutions", 0) or 0) * 100
            }
    except Exception:
        pass
    return None

def calculate_structural_support(df):
    try:
        if df is None or df.empty or len(df) < 20:
            fallback_price = float(df['Close'].iloc[-1]) * 0.95 if df is not None and not df.empty else 0.0
            return round(fallback_price, 2), "基礎價格支撐"

        calc_df = df.copy()
        current_close = float(calc_df['Close'].iloc[-1])

        ma20 = float(calc_df['Close'].tail(20).mean())
        ma60 = float(calc_df['Close'].tail(60).mean()) if len(calc_df) >= 60 else ma20

        calc_df['Prev_Close'] = calc_df['Close'].shift(1)
        calc_df['TR1'] = calc_df['High'] - calc_df['Low']
        calc_df['TR2'] = (calc_df['High'] - calc_df['Prev_Close']).abs()
        calc_df['TR3'] = (calc_df['Low'] - calc_df['Prev_Close']).abs()
        calc_df['TR'] = calc_df[['TR1', 'TR2', 'TR3']].max(axis=1)
        atr_14 = float(calc_df['TR'].tail(14).mean())

        highest_close_20 = float(calc_df['Close'].tail(20).max())
        atr_support = highest_close_20 - (2.5 * atr_14)

        if current_close >= ma60 * 1.10:
            structural_support = max(ma60, (ma20 * 0.5 + atr_support * 0.5))
            logic_desc = f"波段多頭結構｜結合 20MA留倉線 ({round(ma20, 1)}元) 與 ATR波動底線 ({round(atr_support, 1)}元)"
        else:
            structural_support = ma60
            logic_desc = f"中長線價值中樞｜以 60MA季線實質留倉成本 ({round(ma60, 1)}元) 為關鍵多空分水嶺"

        return round(float(structural_support), 2), logic_desc

    except Exception:
        fallback = float(df['Close'].iloc[-1]) * 0.95 if df is not None and not df.empty else 0.0
        return round(fallback, 2), "系統預設支撐"

def get_financial_margin_trend(sid):
    if sid in _FIN_TREND_CACHE:
        return _FIN_TREND_CACHE[sid]

    raw_sid = str(sid).split('(')[0].split(' ')[0].strip()
    
    if ".TW" in raw_sid.upper() or ".TWO" in raw_sid.upper():
        candidate_tickers = [raw_sid]
    else:
        suffixes = [".TWO", ".TW"] if raw_sid in ["3595", "7853", "3081"] or len(raw_sid) == 6 else [".TW", ".TWO"]
        candidate_tickers = [f"{raw_sid}{s}" for s in suffixes]

    pure_num = raw_sid.split('.')[0]
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
        _FIN_TREND_CACHE[sid] = result
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
                        q_label = f"{col.year}Q{(col.month-1)//3 + 1}"
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
                    result["diagnosis_text"] = f"跨年毛利 {result['gm_3y_diff']:+.2f}% | 年度營收 {result['annual_rev_cagr']:+.1f}% (長線與單季同步擴張)"
                elif result["is_long_term_growth"] and is_recent_q_dip:
                    result["is_q_dip_opportunity"] = True
                    result["status_tag"] = "💎 長線成長・單季逆風黃金坑"
                    result["diagnosis_text"] = f"跨年毛利 {result['gm_3y_diff']:+.2f}% | 年度營收 {result['annual_rev_cagr']:+.1f}% (單季淡季休整，全年趨勢向上)"
                else:
                    result["status_tag"] = "⚠️ 長線毛利或營收趨緩"
                    result["diagnosis_text"] = f"跨年毛利 {result['gm_3y_diff']:+.2f}% | 年度營收 {result['annual_rev_cagr']:+.1f}% (嚴守技術籌碼防線)"
                break
        except Exception:
            continue

    _FIN_TREND_CACHE[sid] = result
    return result

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

def send_discord_webhook(webhook_url, embed_data):
    if not webhook_url:
        return False
    try:
        if isinstance(embed_data, str):
            payload = {"content": embed_data}
        else:
            payload = {"embeds": [embed_data]}
        response = requests.post(webhook_url, json=payload, timeout=5)
        return response.status_code in [200, 204]
    except Exception as e:
        print(f"發送 Discord 失敗: {e}")
        return False

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

# ==============================================================================
# 💥 【V37.0 升級：大盤自適應雙軌分流監控引擎】
# ==============================================================================
def scan_and_notify(sid, sname, webhook_url, is_full_market=False, market_regime=None):
    df_scan = get_stock_df(sid)
    if df_scan.empty or len(df_scan) < 20:
        return False
    
    last, prev = df_scan.iloc[-1], df_scan.iloc[-2]
    a_data = get_analysis_data(sid)
    fin_trend = None
    
    if market_regime is None:
        market_regime = {"mode": "BULL", "allow_breakout": True, "allow_bottom_fish": True}

    # === 🛡️ 大盤自適應雙軌分流前置濾網 ===
    if is_full_market:
        try:
            vol_ma20 = df_scan['Volume'].rolling(20).mean().iloc[-1]
            if pd.isna(vol_ma20) or vol_ma20 < 800:
                return False
            ma20 = last.get('MA20', 0)
            ma60 = last.get('MA60', 0)
            ma240 = last.get('MA240', 0)
            current_price_fast = float(last['Close'])
            macd_hist = last.get('MACD_Hist', 0)
            rsi_val = last.get('RSI', 50)
            
            # 軌道 A：右側順勢進攻軌
            is_right_track = (
                market_regime["allow_breakout"]
                and pd.notna(ma20) and pd.notna(ma60) and pd.notna(ma240) and ma240 > 0
                and (current_price_fast > ma20 > ma60 > ma240)
                and (macd_hist >= 0)
            )
            if market_regime["mode"] == "PULLBACK":
                pass

            # 軌道 B：左側深水撈底軌 (專抓潛龍與底背離)
            is_left_track = (
                market_regime["allow_bottom_fish"]
                and pd.notna(ma60) and pd.notna(ma240) and ma240 > 0
                and (ma60 >= ma240)
                and (current_price_fast >= ma240 * 0.97)
                and (rsi_val <= 40)
            )

            if not (is_right_track or is_left_track):
                return False

            inst_val = a_data['法人持股'] if (a_data and '法人持股' in a_data) else 0
            eps_val = a_data['EPS'] if (a_data and 'EPS' in a_data) else "N/A"
            rev_growth = a_data['營收成長率'] if (a_data and '營收成長率' in a_data) else "N/A"
            
            if inst_val < 3.0:  # 稍微放寬撈底時的法人門檻
                return False
            if eps_val == "N/A" or float(eps_val) <= 0:
                return False
            
            is_rev_ok = (rev_growth != "N/A" and float(rev_growth) > 0)
            if not is_rev_ok:
                fin_trend = get_financial_margin_trend(sid)
                if not fin_trend["is_long_term_growth"]:
                    return False
        except Exception:
            pass

    # === 數據計算 ===
    clean_prices = get_yahoo_web_quote_from_df(sid, df_scan)
    current_price = clean_prices["current"]
    prev_price = clean_prices["prev_close"]
    
    price_change = round(current_price - prev_price, 2)
    change_pct = round((price_change / prev_price) * 100, 2) if prev_price > 0 else 0.0
    change_sign = "▲" if price_change > 0 else ("▼" if price_change < 0 else " ")
    
    today_volume = last['Volume']
    vol_ma5 = last['Vol_MA5']
    vol_ratio = today_volume / vol_ma5 if vol_ma5 > 0 else 1
    
    inst_val = a_data['法人持股'] if (a_data and '法人持股' in a_data) else 0
    chip_info = f"法人持股 {round(inst_val, 1)}% " + ("(大戶鎖碼)" if inst_val > 25 else "(散戶主導)")

    df_temp = df_scan.copy()
    df_temp['Price_Diff'] = df_temp['Close'].diff()
    df_temp['Net_Force_Vol'] = df_temp.apply(
        lambda r: r['Volume'] if r['Price_Diff'] > 0 else (-r['Volume'] if r['Price_Diff'] < 0 else 0.0), axis=1
    )
    net_5d = round(df_temp['Net_Force_Vol'].tail(5).sum(), 1)
    chip_flow_status = get_institutional_chips(df_scan)

    weighted_support, _ = calculate_structural_support(df_scan)
    support_text = f"🟢 關鍵支撐守住 ({weighted_support} 元)" if current_price >= weighted_support else f"🔴 關鍵支撐失守 ({weighted_support} 元)"
    ma_status = "🔥 強勢多頭 (5 > 10 > 20MA)" if last['MA5'] > last['MA10'] > last['MA20'] else "💤 區間整理"

    # === 訊號判定 ===
    status_msg = "⚖️ 區間溫和"
    signals_triggered = False
    color_hex = 15158332 if price_change >= 0 else 3066993

    if vol_ratio >= 1.15 and market_regime["allow_breakout"]:
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
            is_near_ma60 = abs(current_price - ma60) / ma60 <= 0.06
            is_near_ma240 = abs(current_price - ma240) / ma240 <= 0.06
            if (is_near_ma60 or is_near_ma240) and (today_volume < vol_ma20 * 0.5) and (last['RSI'] <= 35) and ("倒貨" not in chip_flow_status):
                if vol_ma20 > 250 and inst_val > 1.0:
                    support_type = "年線(240MA)" if is_near_ma240 else "季線(60MA)"
                    status_msg = f"🐉【深水區潛龍】測 {support_type} (籌碼安全)！"
                    color_hex = 16766720
                    signals_triggered = True
    except Exception:
        pass
        
    if not signals_triggered and len(df_scan) >= 10:
        past_min_close = df_scan.iloc[-10:-1]['Close'].min()
        past_min_rsi = df_scan.iloc[-10:-1]['RSI'].min()
        if (current_price <= past_min_close) and (last['RSI'] > past_min_rsi) and (last['RSI'] < 40) and ("倒貨" not in chip_flow_status):
            status_msg = "🔥【低檔底背離】下跌力道竭盡，醞釀強彈！"
            color_hex = 16744192
            signals_triggered = True

    # === 組合結果並回傳 ===
    if signals_triggered:
        if fin_trend is None:
            fin_trend = get_financial_margin_trend(sid)

        score = calculate_composite_score(
            net_5d,
            vol_ratio,
            is_long_term_growth=fin_trend["is_long_term_growth"],
            is_q_dip=fin_trend["is_q_dip_opportunity"],
            signal_type=status_msg
        )

        ann_gm_str = " ➔ ".join([f"{k[-2:]}年:{v}%" for k, v in fin_trend["annual_gm_dict"].items()]) if fin_trend["annual_gm_dict"] else f"最新: {fin_trend['latest_gm']}"
        q_gm_str = " ➔ ".join([f"{k[-2:]}:{v}%" for k, v in fin_trend["quarterly_gm_dict"].items()]) if fin_trend["quarterly_gm_dict"] else "暫無季序列"

        alert_description = f"🔥 **綜合火力評分：{score} 分**\n\n"
        alert_description += f"🔗 [點擊前往 Yahoo 股市查看 {sname}](https://tw.stock.yahoo.com/quote/{sid})\n\n"
        alert_description += f"**表面型態**：**`{status_msg}`**"

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
    
    return False

def run_all_scan():
    print(f"[{datetime.datetime.now()}] 開始執行背景自動掃描...")
    
    TEST_MODE = False
    stock_dict = load_stock_dict()
    
    if not stock_dict:
        print("名單為空，停止掃描。")
        return

    if TEST_MODE:
        print("⚠️ [測試模式開啟]：只掃描前 5 檔，不執行全體掃描。")
        items = list(stock_dict.items())[:5]
        stock_dict = dict(items)

    is_full_market = len(stock_dict) > 500
    
    # 🧭 自動偵測大盤位階與導航狀態
    market_regime = get_market_regime()
    print(f"🧭 [大盤自適應導航] 目前判定狀態：{market_regime['label']}")

    daily_candidates = []
    elite_dict = {}

    for sid, sname in stock_dict.items():
        try:
            result = scan_and_notify(sid, sname, DEFAULT_DISCORD_WEBHOOK, is_full_market, market_regime)
            if isinstance(result, dict):
                daily_candidates.append(result)
                elite_dict[sid] = sname
                print(f"✅ {sname} 過關！分數：{result['score']}")
            time.sleep(0.2)
        except Exception as e:
            print(f"掃描 {sid} 發生錯誤: {e}")

    if is_full_market and elite_dict:
        try:
            with open("radar_elite.json", "w", encoding="utf-8") as f:
                json.dump(elite_dict, f, ensure_ascii=False, indent=4)
        except Exception as e:
            print(f"寫入 radar_elite.json 失敗: {e}")

    if daily_candidates:
        daily_candidates.sort(key=lambda x: x['score'], reverse=True)
        
        last_day_path = "tracker_state.json"
        tracker_data = {}
        if os.path.exists(last_day_path):
            try:
                with open(last_day_path, 'r', encoding='utf-8') as f:
                    tracker_data = json.load(f)
            except Exception:
                pass
        
        last_scan_date = tracker_data.get("date", "")
        last_day_signals = tracker_data.get("signals", {})
        
        tz_tw = datetime.timezone(datetime.timedelta(hours=8))
        today_date_str = datetime.datetime.now(tz_tw).strftime('%Y-%m-%d')
        new_signals = {}
        
        for stock in daily_candidates:
            ticker = stock['sid']
            signal_type = stock['status_msg']
            
            # 1. 完整記錄歷史 CSV
            log_signal_to_csv(stock['sid'], stock['sname'], stock['current_price'], stock['embed'])
            
            # 2. 跨日連續通報
            if last_scan_date != today_date_str:
                if ticker in last_day_signals and last_day_signals[ticker] == signal_type:
                    send_discord_webhook(DEFAULT_DISCORD_WEBHOOK, f"🔥 **【連續鎖碼通知】** {stock['sname']} 連續多日維持 {signal_type}！")
            
            new_signals[ticker] = signal_type

            # 3. 雙管齊下：嚴選 Top 5 且總分 >= 25 分才推播
            if stock in daily_candidates[:5] and stock['score'] >= 25.0:
                is_duplicate_today = (last_scan_date == today_date_str) and (last_day_signals.get(ticker) == signal_type)
                if not is_duplicate_today:
                    send_discord_webhook(DEFAULT_DISCORD_WEBHOOK, stock['embed'])
                else:
                    print(f"🛑 攔截重複推播：{stock['sname']} 今日已發送過相同狀態。")
                time.sleep(1)
        
        with open(last_day_path, 'w', encoding='utf-8') as f:
            json.dump({"date": today_date_str, "signals": new_signals}, f, ensure_ascii=False)
        print("✅ 今日全體記錄與精華推播完成！")

if __name__ == "__main__":
    print("DEBUG: 程式已啟動，準備進入 run_all_scan...")
    try:
        run_all_scan()
        print("DEBUG: run_all_scan 執行結束。")
    except Exception as e:
        print(f"DEBUG: 發生嚴重錯誤: {e}")
