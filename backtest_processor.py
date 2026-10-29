# ==============================================================================
# 🐎 黑馬雷達專用：量化回測未來績效自動回補引擎 (V7.1 靜默清理舊資料與精準勝率版)
# ==============================================================================
import pandas as pd
import numpy as np
import yfinance as yf
import os
import time

# 僅保留最近 N 天的穩定通報資料 (早於此天數的舊版不完整條件資料直接刪除)
KEEP_RECENT_DAYS = 45
# 同一檔股票在 N 天內重複通報時，只保留第一筆起漲訊號
COOLDOWN_DAYS = 5

def run_radar_backtest():
    log_file = "signal_history.csv"
    output_file = "signal_history_backtest.csv"

    if not os.path.exists(log_file):
        print(f"❌ 錯誤：找不到來源檔案【{log_file}】！")
        return

    print("📂 成功讀取資料庫，正在自動清理舊資料與重複雜訊...")
    df = pd.read_csv(log_file, encoding="utf-8-sig", on_bad_lines="skip")
    df.columns = [c.strip() for c in df.columns]

    required_cols = ["日期時間", "股票代號", "觸發價格"]
    for col in required_cols:
        if col not in df.columns:
            print(f"❌ 錯誤：缺少必要欄位【{col}】！")
            return

    # 1. 清理代號與異常價格
    df["股票代號"] = df["股票代號"].astype(str).str.strip().str.split(".").str[0].str.strip()
    df["觸發價格"] = pd.to_numeric(df["觸發價格"], errors="coerce")
    df["_dt"] = pd.to_datetime(df["日期時間"], errors="coerce")
    df = df.dropna(subset=["_dt", "觸發價格", "股票代號"])
    df = df[df["觸發價格"] > 0].sort_values("_dt", ascending=True).reset_index(drop=True)

    # 2. 直接刪除早期舊資料，僅保留近期條件最穩定的通報紀錄
    if not df.empty and KEEP_RECENT_DAYS > 0:
        cutoff_date = (df["_dt"].max() - pd.Timedelta(days=KEEP_RECENT_DAYS)).date()
        df = df[df["_dt"].dt.date >= cutoff_date].copy()

    # 3. 同股 5 日冷卻去重 (只留第一根起漲通報)
    kept_indices = []
    last_trigger = {}
    for idx, row in df.iterrows():
        sid = row["股票代號"]
        t_date = row["_dt"].date()
        if sid not in last_trigger or (t_date - last_trigger[sid]).days >= COOLDOWN_DAYS:
            kept_indices.append(idx)
            last_trigger[sid] = t_date
    df = df.loc[kept_indices].reset_index(drop=True)

    period_map = {
        "T+1 報酬率(%)": 1,
        "T+3 報酬率(%)": 3,
        "T+5 報酬率(%)": 5,
        "T+10 報酬率(%)": 10,
        "T+20 報酬率(%)": 20
    }
    # 未到期一律設為 np.nan，不填 0.0 避免拉低勝率
    for col in period_map.keys():
        df[col] = np.nan

    total_signals = len(df)
    print(f"🎬 清理完成！保留近期穩定訊號共 {total_signals} 筆，開始執行績效回補...\n")

    history_cache = {}
    valid_rows = []

    for idx, row in df.iterrows():
        pure_sid = str(row["股票代號"]).strip()
        trigger_price = float(row["觸發價格"])
        trigger_date = row["_dt"].date()

        suffixes = [".TWO", ".TW"] if pure_sid in ["3595", "7853", "3081"] or len(pure_sid) == 6 else [".TW", ".TWO"]
        candidate_tickers = [f"{pure_sid}{s}" for s in suffixes]

        stock_data = history_cache.get(pure_sid, pd.DataFrame())
        if stock_data.empty:
            for ticker_id in candidate_tickers:
                try:
                    temp_data = yf.download(ticker_id, period="1y", progress=False)
                    if temp_data is not None and not temp_data.empty:
                        if isinstance(temp_data.columns, pd.MultiIndex):
                            temp_data.columns = temp_data.columns.get_level_values(0)
                        stock_data = temp_data
                        history_cache[pure_sid] = stock_data
                        break
                except Exception:
                    continue
            time.sleep(0.12)

        if stock_data.empty:
            continue

        future_data = stock_data[stock_data.index.date > trigger_date]
        if future_data.empty:
            continue

        valid_rows.append(idx)
        for col_name, day_offset in period_map.items():
            if len(future_data) >= day_offset:
                target_close = float(future_data["Close"].iloc[day_offset - 1])
                df.at[idx, col_name] = round(((target_close - trigger_price) / trigger_price) * 100, 2)

        print(f" 🟩 [{idx+1}/{total_signals}] 股票 {pure_sid} | 觸發日: {trigger_date} | 回補完成")

    # 只輸出有效結算的乾淨資料列
    df_clean = df.loc[valid_rows].drop(columns=["_dt"], errors="ignore").reset_index(drop=True)
    df_clean.to_csv(output_file, index=False, encoding="utf-8-sig")
    print(f"\n🎉 清理與回補完成！已輸出純淨回測報表：【{output_file}】（共 {len(df_clean)} 筆有效訊號）")

if __name__ == "__main__":
    run_radar_backtest()
