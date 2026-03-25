import requests
import pandas as pd
import yfinance as yf
import datetime
import sys
import io
import os

# --- 0. 環境與編碼設定 ---
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# 安全讀取 Webhook
WEBHOOK_URL = os.environ.get('DISCORD_WEBHOOK', "https://discord.com/api/webhooks/1327117130457419796/JSe6r-07pEwpNU0nYwFYCn-PDEtuYpMduLUZEivXYsbi0AzHHIVOsxyFAp_x5Dd3iaJM")

# 監控清單：股號 + 公司名稱與產業標籤
WATCH_LIST = {
    "3595": "3595 山太士 [偏光片]",
    "3450": "3450 聯鈞 [光通訊/封測]",
    "3037": "3037 欣興 [IC載板]",
    "2330": "2330 台積電 [半導體代工]",
    "3363": "3363 上詮 [光通訊/CPO]",
    "6451": "6451 訊芯-KY [封測/CPO]",
    "3163": "3163 波若威 [光通訊]",
    "4979": "4979 華星光 [光通訊]",
    "3081": "3081 聯亞 [光通訊/雷射]",
    "2455": "2455 全新 [磊晶/PA]",
    "6442": "6442 光聖 [光通訊/濾波器]"
}

# --- 1. Discord 發送函數 ---
def send_discord(stock_display_name, price, rsi, vol_ratio, status_tag, ma_info, chip_info, alert_lights):
    # 根據 RSI 決定顏色 (紅:過熱, 綠:安全)
    if rsi > 80: color = 15158332 
    elif rsi < 40: color = 3066993  
    else: color = 15844367 
    
    payload = {
        "username": "秉諺的黑馬雷達 V15.7",
        "embeds": [{
            "title": f"🚀 戰情室訊號觸發：{stock_display_name}",
            "color": color,
            "fields": [
                {"name": "目前股價", "value": f"**{price}** TWD", "inline": True},
                {"name": "量能爆發", "value": f"🔥 **{round(vol_ratio, 2)}** 倍", "inline": True},
                {"name": "RSI 指數", "value": f"{round(rsi, 2)}", "inline": True},
                {"name": "均線狀態", "value": f"📊 {ma_info}", "inline": False},
                {"name": "技術/趨勢", "value": f"⚡ {status_tag}", "inline": True},
                {"name": "籌碼分析", "value": f"💎 {chip_info}", "inline": True},
                {"name": "財報警示燈", "value": alert_lights, "inline": False}
            ],
            "footer": {"text": f"偵測時間：{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"}
        }]
    }
    try:
        resp = requests.post(WEBHOOK_URL, json=payload, timeout=10)
        if resp.status_code == 204:
            print(f"✅ {stock_display_name} 通知發送成功！")
    except Exception as e:
        print(f"❌ Discord 發送失敗: {e}")

# --- 2. 掃描核心邏輯 ---
def run_scan():
    print("="*50)
    print(f"🚀 啟動 V15.7 黑馬雷達 (自動識別名稱與產業)")
    print("="*50)
    
    for s_id, s_display_name in WATCH_LIST.items():
        df = pd.DataFrame()
        found = False
        # 自動嘗試上市(.TW)或上櫃(.TWO)
        for suffix in [".TWO", ".TW"]:
            try:
                ticker_sym = f"{s_id}{suffix}"
                ticker = yf.Ticker(ticker_sym)
                df = ticker.history(period="60d", auto_adjust=True)
                if not df.empty and len(df) >= 35:
                    found = True
                    break
            except: continue
        
        if not found:
            print(f"⚠️ {s_id} 無法抓取資料")
            continue
            
        try:
            # 處理資料格式
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
            inst_val = info.get("heldPercentInstitutions", 0) * 100
            rev_growth = info.get('revenueGrowth', 0)
            debt_ratio = info.get('debtToEquity', 0)
            
            rev_light = "🔴營收衰退" if (isinstance(rev_growth, (int, float)) and rev_growth < 0) else "✅營收穩健"
            debt_light = "🔴負債過高" if (isinstance(debt_ratio, (int, float)) and debt_ratio > 60) else "✅財務安全"
            alert_lights = f"{rev_light} | {debt_light}"
            chip_info = f"法人 {round(inst_val, 1)}% " + ("(大戶鎖碼)" if inst_val > 25 else "(散戶主導)")

            print(f"🔍 檢查 {s_display_name} | 量比: {round(ratio, 2)}x")

            # --- 觸發判定 ---
            # 門檻：量比 > 1.3 且 (今日 MACD 金叉 或 爆量且收在 5MA 之上)
            if ratio >= 1.3:
                price_now = float(close.iloc[-1])
                status_tag = "🟢 MACD 金叉發動" if is_macd_cross else "🔥 爆量起漲"
                send_discord(s_display_name, round(price_now, 2), rsi, ratio, status_tag, ma_info, chip_info, alert_lights)
                print(f"🎯 {s_display_name} 訊號達成，已發送 Discord！")

        except Exception as e:
            print(f"⚠️ {s_id} 處理出錯: {e}")

if __name__ == "__main__":
    run_scan()