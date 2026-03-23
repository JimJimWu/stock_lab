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

# --- 2. Discord 發送格式 ---
def send_discord(stock_id, price, rsi, vol_ratio, status_tag, ma5, chip_info):
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
                {"name": "量能爆發", "value": f"🔥 **{round(vol_ratio, 2)}** 倍", "inline": False},
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

# --- 3. 掃描核心邏輯 (雲端優化版) ---
def run_scan():
    print(f"[{datetime.datetime.now()}] 啟動 V7.8 雲端穩定掃描...")
    for s in WATCH_LIST:
        df = pd.DataFrame()
        for suffix in [".TWO", ".TW"]:
            try:
                # 使用 download 搭配 auto_adjust 在雲端更穩定
                temp_df = yf.download(f"{s}{suffix}", period="1y", progress=False, auto_adjust=True)
                if not temp_df.empty:
                    # 強制處理可能的多層索引
                    if isinstance(temp_df.columns, pd.MultiIndex):
                        temp_df.columns = temp_df.columns.get_level_values(0)
                    # 統一欄位名稱格式
                    temp_df.columns = [str(c).strip().capitalize() for c in temp_df.columns]
                    if 'Close' in temp_df.columns and len(temp_df) >= 30:
                        df = temp_df
                        break
            except:
                continue
        
        if df.empty: continue
        
        try:
            # 數值抓取
            close = df['Close']
            vol = df['Volume']
            
            # 計算指標
            ma5 = float(close.rolling(5).mean().iloc[-1])
            vol_ma5 = float(vol.rolling(5).mean().iloc[-1])
            
            # MACD
            exp1 = close.ewm(span=12, adjust=False).mean()
            exp2 = close.ewm(span=26, adjust=False).mean()
            macd_hist = (exp1 - exp2) - (exp1 - exp2).ewm(span=9, adjust=False).mean()
            h_prev, h_curr = float(macd_hist.iloc[-2]), float(macd_hist.iloc[-1])
            
            # RSI
            delta = close.diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
            rsi = float((100 - (100 / (1 + gain/loss))).iloc[-1])
            
            # 籌碼模擬
            price_change = float(close.iloc[-1]) - float(close.iloc[-2])
            chip_info = "💎 法人/大戶買盤強勁" if price_change > 0 else "⚡ 散戶衝進去接刀/出貨"

            # 判定邏輯
            ratio = float(vol.iloc[-1]) / vol_ma5 if vol_ma5 > 0 else 0
            
            if ratio >= 1.5:
                if h_prev <= 0 and h_curr > 0:
                    tag = "🔥 金叉起漲"
                elif h_curr > 0:
                    tag = "📈 多頭續強"
                else:
                    tag = "📉 跌勢放量"
                
                send_discord(s, round(float(close.iloc[-1]), 2), rsi, ratio, tag, ma5, chip_info)
                print(f"🚨 訊號觸發：{s}")
        except Exception as e:
            print(f"處理 {s} 時出錯: {e}")

if __name__ == "__main__":
    run_scan()
