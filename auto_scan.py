import yfinance as yf
import pandas as pd
import requests
from datetime import datetime
import os

# --- 1. 標的配置 ---
STOCK_DICT = {
    "3595": "3595 (山太士)", "3450": "3450 (聯鈞)", "3037": "3037 (欣興)", 
    "2330": "2330 (台積電)", "3363": "3363 (上詮)", "6451": "6451 (訊芯-KY)", 
    "3163": "3163 (波若威)", "4979": "4979 (華星光)", "3081": "3081 (聯亞)", 
    "2455": "2455 (全新)", "6442": "6442 (光聖)",
    "2486": "2486 (一銓)", "3714": "3714 (富采)", "1802": "1802 (台玻)",
    "2408": "2408 (南亞科)", "1815": "1815 (富喬)", "4958": "4958 (臻鼎-KY)"
}

DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK", "你的_WEBHOOK_網址")

def send_discord(name, price, rsi, ratio, status, ma, chip, alerts):
    content = (
        f"🔔 **【黑馬雷達掃描報告】**\n"
        f"🎯 **標的：** {name}\n"
        f"💰 **現價：** `{price}` | **RSI：** `{round(rsi, 1)}` | **量比：** `{round(ratio, 2)}x`\n"
        f"🚦 **狀態：** {status}\n"
        f"📊 **均線：** {ma}\n"
        f"👥 **籌碼：** {chip}\n"
        f"📢 **財務：** {alerts}\n"
        f"⏰ **時間：** {datetime.now().strftime('%m/%d %H:%M')}"
    )
    payload = {"content": content}
    requests.post(DISCORD_WEBHOOK_URL, json=payload)

def run_scan():
    print(f"🚀 開始深度掃描: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    for sid, name in STOCK_DICT.items():
        try:
            # 判斷上市/上櫃
            symbol = f"{sid}.TWO" if sid.startswith(('3', '6', '8')) else f"{sid}.TW"
            ticker = yf.Ticker(symbol)
            df = ticker.history(period="1y", auto_adjust=True)
            
            if df.empty or len(df) < 30: continue
            
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            
            close = df['Close']
            
            # --- 技術指標：MACD ---
            exp1 = close.ewm(span=12, adjust=False).mean()
            exp2 = close.ewm(span=26, adjust=False).mean()
            dif = exp1 - exp2
            dea = dif.ewm(span=9, adjust=False).mean()
            is_macd_cross = (dif.iloc[-1] > dea.iloc[-1]) and (dif.iloc[-2] <= dea.iloc[-2])
            
            # --- 技術指標：RSI 與 均線 ---
            delta = close.diff()
            gain = (delta.where(delta > 0, 0)).rolling(14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
            rsi = float((100 - (100 / (1 + (gain/loss)))).iloc[-1])
            
            ma5 = close.rolling(5).mean().iloc[-1]
            ma10 = close.rolling(10).mean().iloc[-1]
            ma20 = close.rolling(20).mean().iloc[-1]
            
            if ma5 > ma10 > ma20: ma_info = "🔥 強勢多頭 (5>10>20)"
            elif ma5 > ma10: ma_info = "📈 短線轉強 (5>10)"
            else: ma_info = "💤 震盪盤整中"

            # --- 量能與籌碼 ---
            vol_ma5 = df['Volume'].rolling(5).mean().iloc[-1]
            ratio = float(df['Volume'].iloc[-1]) / vol_ma5 if vol_ma5 > 0 else 0
            
            info = ticker.info
            inst_val = (info.get("heldPercentInstitutions", 0) or 0) * 100
            rev_growth = info.get('revenueGrowth', 0)
            debt_ratio = info.get('debtToEquity', 0)
            
            # 財務燈號
            rev_light = "🔴營收衰退" if (isinstance(rev_growth, (int, float)) and rev_growth < 0) else "✅營收穩健"
            debt_light = "🔴負債過高" if (isinstance(debt_ratio, (int, float)) and debt_ratio > 60) else "✅財務安全"
            alert_lights = f"{rev_light} | {debt_light}"
            chip_info = f"法人 {round(inst_val, 1)}% " + ("(大戶鎖碼)" if inst_val > 25 else "(散戶主導)")

            print(f"🔍 檢查 {name} | 量比: {round(ratio, 2)}x")

            # --- 觸發判定 ---
            # 門檻：量比 > 1.3 且 (今日 MACD 金叉 或 爆量且收在 5MA 之上)
            if ratio >= 1.3:
                price_now = float(close.iloc[-1])
                status_tag = "🟢 MACD 金叉發動" if is_macd_cross else "🔥 爆量起漲 (量比 > 1.3)"
                
                # 發送 Discord
                send_discord(name, round(price_now, 2), rsi, ratio, status_tag, ma_info, chip_info, alert_lights)
                print(f"🎯 {name} 訊號達成，已發送 Discord！")

        except Exception as e:
            print(f"⚠️ {sid} 處理出錯: {e}")

if __name__ == "__main__":
    run_scan()