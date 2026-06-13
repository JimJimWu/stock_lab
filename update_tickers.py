# ==============================================================================
# 秉諺的黑馬雷達 - 全台股母體名單自動擷取器 (update_tickers.py V1.1 偽裝突破版)
# ==============================================================================
import json
import requests
import datetime

OUTPUT_FILE = "stock_dict.json"

# 💥 偽裝成一般使用者的瀏覽器，降低被證交所防火牆阻擋的機率
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

def fetch_twse_stocks():
    print("📡 正在連接台灣證交所 (TWSE) 官方資料庫...")
    url = "https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL"
    try:
        response = requests.get(url, headers=HEADERS, timeout=15)
        response.raise_for_status()
        data = response.json()
        
        stock_dict = {}
        for item in data:
            sid = str(item.get("Code", "")).strip()
            # 💥 順手淨化：移除股票名稱尾部的 '*' 符號
            sname = str(item.get("Name", "")).strip().replace("*", "")
            
            if len(sid) == 4 and sid.isdigit() and not sid.startswith("00"):
                stock_dict[sid] = sname
                
        print(f"✅ 成功取得 {len(stock_dict)} 檔 [上市] 股票。")
        return stock_dict
    except Exception as e:
        print(f"❌ 上市名單抓取失敗 (可能遭海外 IP 阻擋): {e}")
        return {}

def fetch_tpex_stocks():
    print("📡 正在連接櫃買中心 (TPEx) 官方資料庫...")
    url = "https://www.tpex.org.tw/openapi/v1/tpex_mainboard_quotes"
    try:
        response = requests.get(url, headers=HEADERS, timeout=15)
        response.raise_for_status()
        data = response.json()
        
        stock_dict = {}
        for item in data:
            sid = str(item.get("SecuritiesCompanyCode", "")).strip()
            # 💥 順手淨化
            sname = str(item.get("CompanyName", "")).strip().replace("*", "")
            
            if len(sid) == 4 and sid.isdigit() and not sid.startswith("00"):
                stock_dict[sid] = sname
                
        print(f"✅ 成功取得 {len(stock_dict)} 檔 [上櫃] 股票。")
        return stock_dict
    except Exception as e:
        print(f"❌ 上櫃名單抓取失敗: {e}")
        return {}

def main():
    print(f"[{datetime.datetime.now()}] 開始執行全台股名單更新...")
    twse_stocks = fetch_twse_stocks()
    tpex_stocks = fetch_tpex_stocks()
    
    all_stocks = {**twse_stocks, **tpex_stocks}
    
    if all_stocks:
        try:
            with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
                json.dump(all_stocks, f, ensure_ascii=False, indent=4)
            print(f"🎉 更新完成！共計 {len(all_stocks)} 檔純淨股票已寫入 {OUTPUT_FILE}")
        except Exception as e:
            print(f"❌ 寫入檔案失敗: {e}")
    else:
        print("⚠️ 警告：未能抓取到任何資料。")

if __name__ == "__main__":
    main()
