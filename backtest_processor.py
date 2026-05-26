# ==============================================================================
# 🐎 黑馬雷達專用：量化回測未來績效自動回補引擎 (V1.0)
# ==============================================================================
import pandas as pd
import yfinance as yf
import datetime
import os

def run_radar_backtest():
    log_file = "signal_history.csv"
    output_file = "signal_history_backtest.csv"

    # 1. 安全檢查：確保來源資料庫存在
    if not os.path.exists(log_file):
        print(f"❌ 錯誤：找不到來源檔案【{log_file}】！")
        print("請確保此腳本檔案與您的 signal_history.csv 放在同一個資料夾內。")
        return

    print(f"📂 成功讀取資料庫，正在載入訊號紀錄...")
    df = pd.read_csv(log_file, encoding="utf-8-sig")

    # 2. 欄位合規性檢查
    required_cols = ["日期時間", "股票代號", "觸發價格"]
    for col in required_cols:
        if col not in df.columns:
            print(f"❌ 錯誤：您的 CSV 檔案中缺少必要的欄位【{col}】！請檢查表頭。")
            return

    # 3. 初始化未來績效欄位 (預設為 0.0)
    df["T+1 報酬率(%)"] = 0.0
    df["T+3 報酬率(%)"] = 0.0
    df["T+5 報酬率(%)"] = 0.0

    total_signals = len(df)
    print(f"🎬 開始執行量化未來績效回補，總計 {total_signals} 筆訊號...")

    # 4. 逐筆遍歷訊號，動態回補未來股價
    for idx, row in df.iterrows():
        sid = str(row["股票代號"]).strip()
        trigger_price = float(row["觸發價格"])
        trigger_time_str = str(row["日期時間"])
        
        # 解析觸發當下的日期
        try:
            trigger_date = pd.to_datetime(trigger_time_str).date()
        except Exception:
            print(f"⚠️ 警告: 第 {idx+1} 筆日期格式解析失敗 ({trigger_time_str})，跳過此筆。")
            continue
            
        # 自動修正台股市場後綴
        ticker_id = f"{sid}.TW" if not sid.endswith(('.TW', '.TWO')) else sid
        
        # 設定查詢時間視窗：從觸發當天開始往後抓 15 天，確保扣除例假日後能集齊 5 個交易日
        start_date = trigger_date
        end_date = trigger_date + datetime.timedelta(days=15)
        
        try:
            # 高速抓取特定時間視窗的歷史數據
            stock_data = yf.download(ticker_id, start=start_date, end=end_date, progress=False)
            
            if stock_data.empty:
                continue
                
            # 自動處理新版 yfinance 可能產生的 MultiIndex 欄位架構
            if isinstance(stock_data.columns, pd.MultiIndex):
                stock_data.columns = stock_data.columns.get_level_values(0)
                
            # 關鍵核心：過濾掉觸發當天，只保留「真正的未來交易日」
            future_data = stock_data[stock_data.index.date > trigger_date]
            
            # 5. 精確對齊未來交易日並計算百分比報酬率
            if len(future_data) >= 1:
                t1_close = float(future_data['Close'].iloc[0])
                df.at[idx, "T+1 報酬率(%)"] = round(((t1_close - trigger_price) / trigger_price) * 100, 2)
                
            if len(future_data) >= 3:
                t3_close = float(future_data['Close'].iloc[2])
                df.at[idx, "T+3 報酬率(%)"] = round(((t3_close - trigger_price) / trigger_price) * 100, 2)
                
            if len(future_data) >= 5:
                t5_close = float(future_data['Close'].iloc[4])
                df.at[idx, "T+5 報酬率(%)"] = round(((t5_close - trigger_price) / trigger_price) * 100, 2)
                
            print(f" 🟩 [{idx+1}/{total_signals}] 股票 {sid} | 觸發日: {trigger_date} | 回補完成")
            
        except Exception as e:
            print(f" 🟥 [{idx+1}/{total_signals}] 股票 {sid} 於 {trigger_date} 回補發生異常: {e}")

    # 6. 安全存檔：保留 BOM 標籤確保 Excel 開啟繁體中文完美無亂碼
    df.to_csv(output_file, index=False, encoding="utf-8-sig")
    print(f"\n🎉 量化績效回補大成功！已生成高價值回測報表：【{output_file}】")

if __name__ == "__main__":
    run_radar_backtest()