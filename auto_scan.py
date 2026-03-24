import requests
import pandas as pd
import yfinance as yf
import datetime

# --- 1. 配置 ---
WEBHOOK_URL = "https://discord.com/api/webhooks/1327117130457419796/JSe6r-07pEwpNU0nYwFYCn-PDEtuYpMduLUZEivXYsbi0AzHHIVOsxyFAp_x5Dd3iaJM"
WATCH_LIST = ["3595", "3450", "3037", "2330", "3363", "6451", "3163", "4979", "3081", "2455", "6442"]

# --- 2. 發送邏輯 (升級版) ---
def send_discord(stock_id, price, rsi, vol_ratio, status_tag, ma_info, chip_info, alert_lights):
    # 根據 RSI 決定顏色
    if rsi > 80:
        color = 15158332 # 紅色 (過熱)
    elif rsi < 40:
        color = 3066993  # 綠色 (低檔安全)
    else:
        color = 15844367 # 黃色 (震盪)
    
    payload = {
        "username": "秉諺的黑馬雷達 V15.1",
        "embeds": [{
            "title": f"🚀 戰情室觸發：{stock_id}",
            "color": color,
            "fields": [
                {"name": "目前股價", "value": f"**{price}** TWD", "inline": True},
                {"name": "RSI 指數", "value": f"{round(rsi, 2)}", "inline": True},
                {"name": "量能爆發", "value": f"🔥 **{round(vol_ratio, 2)}** 倍", "inline": True},
                {"name": "均線狀態", "value": f"📊 {ma_info}", "inline": False},
                {"name": "籌碼分析", "value": f"💎 {chip_info}", "inline": True},
                {"name": "技術訊號", "value": status_tag, "inline": True},
                {"name": "財報警示燈", "value": alert_lights, "inline": False} # 補上警示燈
            ],
            "footer": {"text": f"偵測時間：{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"}
        }]
    }
    try:
        resp = requests.post(WEBHOOK_URL, json=payload, timeout=10)
        if resp.status_code == 204:
            print(f"✅ {stock_id} Discord 通知成功！")
    except Exception as e:
        print(f"❌ Discord 發送失敗: {e}")

# --- 3. 掃描核心 (整合 V15.1 邏輯) ---
def run_scan():
    print("="*40)
    print(f"🚀 啟動 V15.1 籌碼財報掃描器")
    print(f"📅 時間：{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*40)
    
    for s in WATCH_LIST:
        df = pd.DataFrame()
        # 抓取數據
        ticker_sym = f"{s}.TW" if not s.startswith('3') else f"{s}.TWO"
        ticker = yf.Ticker(ticker_sym)
        
        try:
            df = ticker.history(period="1y", auto_adjust=True)
            if df.empty or len(df) < 30: continue
            
            # 處理多重索引
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            
            # --- 技術面計算 ---
            close = df['Close']
            ma5, ma10, ma20 = close.rolling(5).mean().iloc[-1], close.rolling(10).mean().iloc[-1], close.rolling(20).mean().iloc[-1]
            vol_ma5 = df['Volume'].rolling(5).mean().iloc[-1]
            ratio = float(df['Volume'].iloc[-1]) / vol_ma5 if vol_ma5 > 0 else 0
            
            # RSI
            delta = close.diff()
            gain = (delta.where(delta > 0, 0)).rolling(14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
            rsi = float((100 - (100 / (1 + (gain/loss)))).iloc[-1])

            # --- 籌碼與財報 (V15.1 核心) ---
            info = ticker.info
            inst_val = info.get("heldPercentInstitutions", 0) * 100
            rev_growth = info.get('revenueGrowth', 0)
            debt_ratio = info.get('debtToEquity', 0)
            
            # 財報警示燈
            rev_light = "🔴營收衰退" if (isinstance(rev_growth, (int, float)) and rev_growth < 0) else "✅營收穩健"
            debt_light = "🔴負債過高" if (isinstance(debt_ratio, (int, float)) and debt_ratio > 60) else "✅財務安全"
            alert_lights = f"{rev_light} | {debt_light}"
            
            # 籌碼描述
            chip_info = f"法人持股 {round(inst_val, 1)}% " + ("(大戶鎖碼)" if inst_val > 25 else "(散戶主導)")
            
            # 均線描述
            if ma5 > ma10 > ma20: ma_info = "🔥 強勢多頭排列 (5>10>20)"
            elif ma5 > ma10: ma_info = "📈 短線轉強 (5>10)"
            else: ma_info = "💤 震盪整理中"

            # --- 觸發條件：爆量 1.5 倍 ---
            if ratio >= 1.5:
                price_now = float(close.iloc[-1])
                tag = "🔥 爆量起漲" if price_now > ma5 else "📉 跌勢放量"
                
                # 發送 Discord
                send_discord(s, round(price_now, 2), rsi, ratio, tag, ma_info, chip_info, alert_lights)
                print(f"🎯 {s} 符合條件，已發送 Discord")
            else:
                print(f"🔍 檢查 {s} | 量比: {round(ratio, 2)} (未達標)")

        except Exception as e:
            print(f"❌ {s} 處理出錯: {e}")

if __name__ == "__main__":
    run_scan()