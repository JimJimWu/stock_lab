# ==============================================================================
# 🐎 黑馬雷達專用：量化回測未來績效自動回補引擎 (V5.0 跨週期多維度版)
# ==============================================================================
import pandas as pd
import yfinance as yf
import datetime
import os
import time
import logging
import warnings
import concurrent.futures

logging.getLogger('yfinance').setLevel(logging.CRITICAL)
warnings.filterwarnings('ignore')

def run_radar_backtest():
    log_file = "signal_history.csv"
    output_file = "signal_history_backtest.csv"

    if not os.path.exists(log_file):
        print(f"❌ 錯誤：找不到來源檔案【{log_file}】！")
        return

    print(f"📂 成功讀取資料庫，正在載入訊號紀錄...")
    df = pd.read_csv(log_file, encoding="utf-8-sig")

    required_cols = ["日期時間", "股票代號", "觸發價格"]
    for col in required_cols:
        if col not in df.columns:
            print(f"❌ 錯誤：缺少必要欄位【{col}】！")
            return

    # 初始化涵蓋短、中期的所有時間維度欄位
    df["T+1 報酬率(%)"] = 0.0
    df["T+3 報酬率(%)"] = 0.0
    df["T+5 報酬率(%)"] = 0.0
    df["T+10 報酬率(%)"] = 0.0 # 💥 新增：兩週波段績效
    df["T+20 報酬率(%)"] = 0.0 # 💥 新增：一個月波段績效

    total_signals = len(df)
    print(f"🎬 開始執行多週期量化績效回補，總計 {total_signals} 筆訊號...\n")

    for idx, row in df.iterrows():
        sid = str(row["股票代號"]).strip()
        trigger_price = float(row["觸發價格"])
        trigger_time_str = str(row["日期時間"])
        
        try:
            trigger_date = pd.to_datetime(trigger_time_str).date()
        except Exception:
            continue
            
        start_date = trigger_date
        # 💥 關鍵修正：觀測視窗由 15 天放寬至 40 天，確保能完整抓取 20 個交易日數據
        end_date = trigger_date + datetime.timedelta(days=40)
        
        suffixes = [".TWO", ".TW"] if sid in ["3595", "7853", "3081"] or len(sid) == 6 else [".TW", ".TWO"]
        
        stock_data = pd.DataFrame()
        for suffix in suffixes:
            ticker_id = f"{sid}{suffix}"
            
            def fetch_data():
                return yf.download(ticker_id, start=start_date, end=end_date, progress=False, show_errors=False)

            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(fetch_data)
                try:
                    temp_data = future.result(timeout=3.0)
                    if not temp_data.empty:
                        if isinstance(temp_data.columns, pd.MultiIndex):
                            temp_data.columns = temp_data.columns.get_level_values(0)
                        stock_data = temp_data
                        break
                except concurrent.futures.TimeoutError:
                    pass
                except Exception:
                    pass
                
        if stock_data.empty:
            print(f" ⚠️ [{idx+1}/{total_signals}] 股票 {sid} | 查無未來數據，跳過。")
            continue
            
        future_data = stock_data[stock_data.index.date > trigger_date]
        
        # 精確計算各個交易日節點的百分比報酬率
        if len(future_data) >= 1:
            t1_close = float(future_data['Close'].iloc[0])
            df.at[idx, "T+1 報酬率(%)"] = round(((t1_close - trigger_price) / trigger_price) * 100, 2)
            
        if len(future_data) >= 3:
            t3_close = float(future_data['Close'].iloc[2])
            df.at[idx, "T+3 報酬率(%)"] = round(((t3_close - trigger_price) / trigger_price) * 100, 2)
            
        if len(future_data) >= 5:
            t5_close = float(future_data['Close'].iloc[4])
            df.at[idx, "T+5 報酬率(%)"] = round(((t5_close - trigger_price) / trigger_price) * 100, 2)

        if len(future_data) >= 10: # 💥 新增：計算第 10 個交易日收盤報酬
            t10_close = float(future_data['Close'].iloc[9])
            df.at[idx, "T+10 報酬率(%)"] = round(((t10_close - trigger_price) / trigger_price) * 100, 2)

        if len(future_data) >= 20: # 💥 新增：計算第 20 個交易日收盤報酬
            t20_close = float(future_data['Close'].iloc[19])
            df.at[idx, "T+20 報酬率(%)"] = round(((t20_close - trigger_price) / trigger_price) * 100, 2)
            
        print(f" 🟩 [{idx+1}/{total_signals}] 股票 {sid} | 觸發日: {trigger_date} | 多週期回補完成")
        time.sleep(0.3) 

    df.to_csv(output_file, index=False, encoding="utf-8-sig")
    print(f"\n🎉 量化多週期績效回補大成功！已更新回測報表：【{output_file}】")

if __name__ == "__main__":
    run_radar_backtest()
