# ==============================================================================
# 秉諺的黑馬雷達 - 全台股母體名單自動擷取器 (update_tickers.py V1.0)
# 資料來源: 台灣證交所 (TWSE) & 櫃買中心 (TPEx) 官方 Open Data API
# ==============================================================================
import json
import requests
import datetime

# 輸出檔案名稱 (完美對接 auto_scan.py)
OUTPUT_FILE = "stock_dict.json"

def fetch_twse_stocks():
    """抓取上市股票名單 (TWSE)"""
    print("📡 正在連接台灣證交所 (TWSE) 官方資料庫...")
    url = "https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL"
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        stock_dict = {}
        for item in data:
            sid = str(item.get("Code", "")).strip()
            sname = str(item.get("Name", "")).strip()
            
            # 🛡️ 純淨濾網：只抓 4 碼純數字，且不含 00 開頭 (排除 ETF 與權證特別股)
            if len(sid) == 4 and sid.isdigit() and not sid.startswith("00"):
                stock_dict[sid] = sname
                
        print(f"✅ 成功取得 {len(stock_dict)} 檔 [上市] 股票。")
        return stock_dict
    except Exception as e:
        print(f"❌ 上市名單抓取失敗: {e}")
        return {}

def fetch_tpex_stocks():
    """抓取上櫃股票名單 (TPEx)"""
    print("📡 正在連接櫃買中心 (TPEx) 官方資料庫...")
    url = "https://www.tpex.org.tw/openapi/v1/tpex_mainboard_quotes"
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        stock_dict = {}
        for item in data:
            sid = str(item.get("SecuritiesCompanyCode", "")).strip()
            sname = str(item.get("CompanyName", "")).strip()
            
            # 🛡️ 純淨濾網：只抓 4 碼純數字，且不含 00 開頭
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
    
    # 合併上市與上櫃名單
    all_stocks = {**twse_stocks, **tpex_stocks}
    
    if all_stocks:
        # 將結果存成 JSON 格式，供 auto_scan.py 讀取
        try:
            with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
                json.dump(all_stocks, f, ensure_ascii=False, indent=4)
            print(f"🎉 更新完成！共計 {len(all_stocks)} 檔純淨股票已寫入 {OUTPUT_FILE}")
        except Exception as e:
            print(f"❌ 寫入檔案失敗: {e}")
    else:
        print("⚠️ 警告：未能抓取到任何資料，請檢查網路連線或 API 狀態。")

if __name__ == "__main__":
    main()
