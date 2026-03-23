import yfinance as yf
import pandas as pd
import datetime
import requests

# --- 1. 設定區 ---
WEBHOOK_URL = "https://discord.com/api/webhooks/1327117130457419796/JSe6r-07pEwpNU0nYwFYCn-PDEtuYpMduLUZEivXYsbi0AzHHIVOsxyFAp_x5Dd3iaJM"
WATCH_LIST = [
    "3595", "3037", "2330", "2317", "2454",  # 核心成長股
    "3363", "6451", "3163", "4979", "3450",  # 矽光子精選
    "3081", "2455", "6442"                   # 矽光子延伸
]

# --- 2. Discord 發送格式 (籌碼與預警優化) ---
def send_discord(stock_id, price, rsi, vol_ratio, status_tag, ma5, chip_info):
    # 三色預警邏輯
    if rsi > 85:
        color = 15158332 # 紅色
        warning_prefix = "⚠️【極度過熱·禁止追高】"
    elif rsi > 70:
        color = 15844367 # 黃色
        warning_prefix = "🟡【高檔震盪·注意回檔】"
    else:
        color = 3066993 # 綠色
        warning_prefix = "✅【趨勢安全·量能發動】"
    
    payload = {
        "username": "秉諺的黑馬雷達 V7.8",
        "embeds": [{
            "title": f"{warning_prefix} {stock_id}",
            "color": color,
            "fields": [
                {"name": "目前股價", "value": f"**{price}** TWD", "inline": True},
                {"name": "RSI 指數", "value": f"{round(rsi, 2)}", "inline": True},
                {"name": "5日線支撐", "value": f"{round(ma5, 2)}", "inline": True},
                {"name": "量能爆發", "value": f"🔥 **{round(vol_ratio, 2)}** 倍 (對比5日均量)", "inline": False},
                {"name": "技術訊號", "value": status_tag, "inline": True},
                {"name": "籌碼分析", "value": chip_info, "inline": True}
            ],
            "footer": {"text": f"偵測時間：{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"}
        }]
    }
    try:
        requests.post(WEBHOOK_URL, json=payload, timeout=10)
    except:
        pass

# --- 3. 掃描核心邏輯 ---
def run_scan():
    print(f"[{datetime.datetime.now()}] 啟動 V7.8 籌碼與預警掃描...")
    for s in WATCH_LIST:
        df = pd.DataFrame()
        ticker = None
        for suffix in [".TWO", ".TW"]:
            try:
                ticker = yf.Ticker(f"{s}{suffix}")
                temp_df = ticker.history(period="1y")
                if not temp_df.empty:
                    if isinstance(temp_df.columns, pd.MultiIndex):
                        temp_df.columns = temp_df.columns.get_level_values(0)
                    df = temp_df
                    break
            except:
                continue
        
        if df.empty or len(df) < 30: continue
        
        # 指標計算
        close, vol = df['Close'], df['Volume']
        ma5 = close.rolling(5).mean().iloc[-1]
        vol_ma5 = vol.rolling(5).mean().iloc[-1]
        
        # MACD 判斷
        exp1 = close.ewm(span=12, adjust=False).mean()
        exp2 = close.ewm(span=26, adjust=False).mean()
        macd_hist = (exp1 - exp2) - (exp1 - exp2).ewm(span=9, adjust=False).mean()
        h_prev, h_curr = macd_hist.iloc[-2], macd_hist.iloc[-1]
        
        # RSI
        delta = close.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rsi = (100 - (100 / (1 + gain/loss))).iloc[-1]
        
        # 籌碼面概況 (簡單模擬：若量增且收紅，視為法人偏多)
        price_change = close.iloc[-1] - close.iloc[-2]
        if price_change > 0:
            chip_info = "💎 法人/大戶買盤強勁"
        else:
            chip_info = "⚡ 散戶衝進去接刀/出貨"

        # --- 判定邏輯：量能噴發 1.5 倍 ---
        ratio = float(vol.iloc[-1]) / float(vol_ma5) if vol_ma5 > 0 else 0
        
        if ratio >= 1.5:
            if h_prev <= 0 and h_curr > 0:
                tag = "🔥 金叉起漲"
            elif h_curr > 0:
                tag = "📈 多頭續強"
            else:
                tag = "📉 跌勢放量"
            
            send_discord(s, round(float(close.iloc[-1]), 2), rsi, ratio, tag, ma5, chip_info)
            print(f"🚨 訊號觸發：{s}")

if __name__ == "__main__":
    run_scan()