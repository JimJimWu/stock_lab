# ==============================================================================
# 秉諺的黑馬雷達 - 背景自動無人值守掃描器 (auto_scan.py V35.0 - 綜合火力 Top10 版)
# ==============================================================================
import os
import json
import time
import datetime
import requests
import yfinance as yf
import pandas as pd

# 強制屏蔽 Yahoo 警告
yf.shared._ERRORS = {}

# 取得當前腳本所在的目錄
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DICT_FILE = os.path.join(BASE_DIR, "full_market_dict.json")

DEFAULT_DISCORD_WEBHOOK = os.environ.get("DISCORD_WEBHOOK") or ""

def log_signal_to_csv(sid, sname, price, embed):
    log_file = "signal_history.csv"
    tz_tw = datetime.timezone(datetime.timedelta(hours=8))
    now_time = datetime.datetime.now(tz_tw).strftime('%Y-%m-%d %H:%M:%S')
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
            f.write(f"{now_time},{sid},{pure_sname},{price},{desc.replace(',', '，')},{tech_vol.replace(',', '，')}\n")
    except Exception as e:
        print(f"寫入 CSV 失敗: {e}")

def load_stock_dict():
    if os.path.exists(DICT_FILE):
        try:
            with open(DICT_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"JSON 解析錯誤: {e}")
    return {}

def get_stock_df(sid):
    try:
        ticker = yf.Ticker(sid)
        df = ticker.history(period="2y", auto_adjust=True, timeout=5.0)
        if df is None or df.empty or len(df) < 20: return pd.DataFrame()
        df = df.copy()
        df = df.dropna(subset=['Close'])
        df['Volume'] = df['Volume'] / 1000.0
        df['MA5'] = df['Close'].rolling(5).mean()
        df['MA10'] = df['Close'].rolling(10).mean()
        df['MA20'] = df['Close'].rolling(20).mean()
        df['Vol_MA5'] = df['Volume'].rolling(5).mean()
        delta = df['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        df['RSI'] = 100 - (100 / (1 + (gain / loss.replace(0, 0.00001))))
        return df
    except: return pd.DataFrame()

def send_discord_webhook(webhook_url, embed_data):
    try:
        requests.post(webhook_url, json={"embeds": [embed_data]}, timeout=5)
    except: pass

def calculate_composite_score(net_5d, volume_ratio):
    chip_score = min(max((net_5d / 3000.0) * 100, 0), 100)
    vol_score = min(max((volume_ratio - 1.15) / (3.0 - 1.15) * 100, 0), 100)
    return round((chip_score * 0.6) + (vol_score * 0.4), 2)

def scan_and_notify(sid, sname, is_full_market):
    df = get_stock_df(sid)
    if df.empty: return False
    
    last = df.iloc[-1]
    # 這裡加入簡單的觸發條件測試
    vol_ratio = last['Volume'] / last['Vol_MA5'] if last['Vol_MA5'] > 0 else 1
    
    if last['Close'] > last['MA5'] and vol_ratio >= 1.0:
        score = calculate_composite_score(500, vol_ratio)
        embed = {
            "title": f"🚨 黑馬雷達：{sname} ({sid})",
            "description": f"🔥 **綜合火力評分：{score} 分**\n**狀態**：強勢突破",
            "color": 16711680,
            "fields": [{"name": "現價", "value": str(round(last['Close'], 2)), "inline": True}]
        }
        return {"sid": sid, "sname": sname, "score": score, "current_price": last['Close'], "embed": embed}
    return False

def run_all_scan():
    stock_dict = load_stock_dict()
    # 💥 這裡設定 TEST_MODE 為 True 即可測試前 5 檔
    TEST_MODE = True
    if TEST_MODE:
        stock_dict = dict(list(stock_dict.items())[:5])
    
    daily_candidates = []
    for sid, sname in stock_dict.items():
        res = scan_and_notify(sid, sname, True)
        if isinstance(res, dict):
            daily_candidates.append(res)
        time.sleep(0.2)
        
    if daily_candidates:
        daily_candidates.sort(key=lambda x: x['score'], reverse=True)
        for stock in daily_candidates[:10]:
            send_discord_webhook(DEFAULT_DISCORD_WEBHOOK, stock['embed'])
            log_signal_to_csv(stock['sid'], stock['sname'], stock['current_price'], stock['embed'])

if __name__ == "__main__":
    run_all_scan()
