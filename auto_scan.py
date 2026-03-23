import yfinance as yf
import pandas as pd
import datetime
import requests
import os

# --- 1. 設定區 ---
# 建議檢查此 URL 是否正確
WEBHOOK_URL = "https://discord.com/api/webhooks/1327117130457419796/JSe6r-07pEwpNU0nYwFYCn-PDEtuYpMduLUZEivXYsbi0AzHHIVOsxyFAp_x5Dd3iaJM"

WATCH_LIST = [
    "3595", "3037", "2330", "2317", "2454",  # 核心成長股
    "3363", "6451", "3163", "4979", "3450",  # 矽光子精選
    "3081", "2455", "6442"                   # 矽光子延伸
]

# --- 2. Discord 發送格式 ---
def send_discord(stock_id, price, rsi, vol_ratio, status_tag, ma_info, chip_info):
    if rsi > 85:
        color = 15158332 # 紅色
    elif rsi > 70:
        color = 15844367 # 黃色
    else:
        color = 3066993 # 綠色
    
    payload = {
        "username": "秉諺的黑馬雷達 V7.8",
        "embeds": [{
            "title": f"🚀 訊號觸發：{stock_id}",
            "color": color,
            "fields": [
                {"name": "目前股價", "value": f"**{price}** TWD", "inline": True},
                {"name": "RSI 指數", "value": f"{round(rsi, 2)}", "inline": True},
                {"name": "均線狀態", "value": f"📊 {ma_info}", "inline": False},
                {"name": "量能爆發", "value": f"🔥 **{round(vol_ratio, 2)}** 倍", "inline": True},
                {"name": "技術訊號", "value": status_tag, "inline": True},
                {"name": "籌碼分析", "value": chip_info, "inline": True}
            ],
            "footer": {"text": f"偵測時間：{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"}
        }]
    }
    try:
        resp = requests.post(WEBHOOK_URL, json=payload, timeout=10)
        if resp.status_code == 204:
            print(f"✅ {stock_id} Discord 通知發送成功！")
    except Exception as e:
        print(f"❌ Discord 發送失敗: {e}")

# --- 3. 掃描核心邏輯 ---
def run_scan():
    print(f"========================================")
    print(f"🚀 啟動秉諺的黑馬雷達掃描器 (V7.8)")
    print(f"📅 時間：{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"========================================")
    
    for s in WATCH_LIST:
        df = pd.DataFrame()
        # 嘗試抓取上市或上櫃後綴
        for suffix in [".TWO", ".TW"]:
            try:
                temp_df = yf.download(f"{s}{suffix}", period="1y", progress=False, auto_adjust=True)
                if not temp_df.empty:
                    if isinstance(temp_df.columns, pd.MultiIndex):
                        temp_df.columns = temp_df.columns.get_level_values(0)
                    temp_df.columns = [str(c).strip().capitalize() for c in temp_df.columns]
                    if 'Close' in temp_df.columns and len(temp_df) >= 30:
                        df = temp_df
                        break
            except:
                continue
        
        if df.empty:
            print(f"⚠️ 無法抓取股票資料: {s}")
            continue
        
        try:
            # 數值計算
            close = df['Close']
            vol = df['Volume']
            
            # 均線 MA5, 10, 20
            ma5 = float(close.rolling(5).mean().iloc[-1])
            ma10 = float(close.rolling(10).mean().iloc[-1])
            ma20 = float(close.rolling(20).mean().iloc[-1])
            vol_ma5 = float(vol.rolling(5).mean().iloc[-1])
            
            # RSI
            delta = close.diff()
            gain = (delta.where(delta > 0, 0)).rolling(14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
            rsi = float((100 - (100 / (1 + gain/loss))).iloc[-1])
            
            # 量比判定
            ratio = float(vol.iloc[-1]) / vol_ma5 if vol_ma5 > 0 else 0
            
            # 螢幕顯示進度
            print(f"🔍 檢查 {s} | 目前價: {round(close.iloc[-1], 2)} | 量比: {round(ratio, 2)}倍")

            # 均線多頭排列描述
            if ma5 > ma10 > ma20:
                ma_info = "🔥 強勢多頭排列 (5>10>20)"
            elif ma5 > ma10:
                ma_info = "📈 短線轉強 (5>10)"
            else:
                ma_info = "💤 震盪整理中"

            # --- 觸發條件：爆量 1.5 倍 ---
            # (測試時可以暫時把 1.5 改成 0.1 看看 Discord 有沒有響)
            if ratio >= 1.5:
                price_now = float(close.iloc[-1])
                chip_info = "💎 大戶買盤強" if price_now > close.iloc[-2] else "⚡ 散戶接刀"
                tag = "🔥 爆量起漲" if price_now > ma5 else "📉 跌勢放量"
                
                send_discord(s, round(price_now, 2), rsi, ratio, tag, ma_info, chip_info)
                
        except Exception as e:
            print(f"❌ 處理 {s} 時發生錯誤: {e}")

    print(f"========================================")
    print(f"✨ 掃描完畢！")

if __name__ == "__main__":
    run_scan()