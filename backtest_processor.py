# ==============================================================================
# 🐎 黑馬雷達專用：量化回測未來績效自動回補引擎 (V6.2 後綴免疫與極速快取版)
# ==============================================================================
import pandas as pd
import yfinance as yf
import datetime
import os
import time

def run_radar_backtest():
    log_file = "signal_history.csv"
    output_file = "signal_history_backtest.csv"

    if not os.path.exists(log_file):
        print(f"❌ 錯誤：找不到來源檔案【{log_file}】！")
        return

    print("📂 成功讀取資料庫，正在載入訊號紀錄...")
    df = pd.read_csv(log_file, encoding="utf-8-sig", on_bad_lines="skip")
    df.columns = [c.strip() for c in df.columns]

    required_cols = ["日期時間", "股票代號", "觸發價格"]
    for col in required_cols:
        if col not in df.columns:
            print(f"❌ 錯誤：缺少必要欄位【{col}】！")
            return

    # 初始化多週期欄位
    period_map = {
        "T+1 報酬率(%)": 1,
        "T+3 報酬率(%)": 3,
        "T+5 報酬率(%)": 5,
        "T+10 報酬率(%)": 10,
        "T+20 報酬率(%)": 20
    }
    for col in period_map.keys():
        if col not in df.columns:
            df[col] = 0.0

    total_signals = len(df)
    print(f"🎬 開始執行多週期量化績效回補，總計 {total_signals} 筆訊號...\n")

    # 記憶體快取：同一檔股票只需下載一次完整區間 K 線，速度提升 10 倍以上
    history_cache = {}

    for idx, row in df.iterrows():
        raw_sid = str(row["股票代號"]).strip()
        try:
            trigger_price = float(row["觸發價格"])
            trigger_date = pd.to_datetime(str(row["日期時間"])).date()
        except Exception:
            continue

        # 💥 【核心修復】：若代號已自帶 .TW 或 .TWO，直接使用，嚴禁重複加上後綴變成 .TW.TW
        if ".TW" in raw_sid.upper() or ".TWO" in raw_sid.upper():
            pure_no = raw_sid.split(".")[0]
            alt_suffix = ".TWO" if raw_sid.upper().endswith(".TW") else ".TW"
            candidate_tickers = [raw_sid, f"{pure_no}{alt_suffix}"]
        else:
            suffixes = [".TWO", ".TW"] if raw_sid in ["3595", "7853", "3081"] or len(raw_sid) == 6 else [".TW", ".TWO"]
            candidate_tickers = [f"{raw_sid}{s}" for s in suffixes]

        pure_sid = raw_sid.split(".")[0]
        # 統一將表格內的股票代號淨化為純數字，防止回測與連續鎖碼分裂
        df.at[idx, "股票代號"] = pure_sid

        stock_data = history_cache.get(pure_sid, pd.DataFrame())
        if stock_data.empty:
            for ticker_id in candidate_tickers:
                try:
                    temp_data = yf.download(ticker_id, period="2y", progress=False)
                    if temp_data is not None and not temp_data.empty:
                        if isinstance(temp_data.columns, pd.MultiIndex):
                            temp_data.columns = temp_data.columns.get_level_values(0)
                        stock_data = temp_data
                        history_cache[pure_sid] = stock_data
                        break
                except Exception:
                    continue
            time.sleep(0.15)

        if stock_data.empty:
            print(f" ⚠️ [{idx+1}/{total_signals}] 股票 {raw_sid} | 查無未來數據，跳過。")
            continue

        future_data = stock_data[stock_data.index.date > trigger_date]
        for col_name, day_offset in period_map.items():
            if len(future_data) >= day_offset:
                target_close = float(future_data["Close"].iloc[day_offset - 1])
                df.at[idx, col_name] = round(((target_close - trigger_price) / trigger_price) * 100, 2)

        print(f" 🟩 [{idx+1}/{total_signals}] 股票 {pure_sid} | 觸發日: {trigger_date} | 多週期回補完成")

    df.to_csv(output_file, index=False, encoding="utf-8-sig")
    print(f"\n🎉 量化多週期績效回補大成功！已更新回測報表：【{output_file}】")

if __name__ == "__main__":
    run_radar_backtest()
