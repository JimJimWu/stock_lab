# ==============================================================================
# 🐎 黑馬雷達專用：量化回測未來績效自動回補引擎 (V7.2 雙檔同步瘦身與新制保護版)
# ==============================================================================
import pandas as pd
import numpy as np
import yfinance as yf
import os
import time

# 1. 新制穩定起算日：直接刪除 2026-09-01 以前舊版「量能爆發突破」格式的歷史舊資料
STABLE_EPOCH_DATE = "2026-09-01"

# 2. 最大保留天數上限 (90天)：確保檔案永遠輕量，不觸發 GitHub 1MB 過大警告，同時保有充足 T+20 樣本
MAX_RETENTION_DAYS = 90

# 3. 同股冷卻去重天數：同一檔股票在 5 天內重複通報時，回測報表僅保留第 1 筆起漲買點
COOLDOWN_DAYS = 5

def run_radar_backtest():
    log_file = "signal_history.csv"
    output_file = "signal_history_backtest.csv"

    if not os.path.exists(log_file):
        print(f"❌ 錯誤：找不到來源檔案【{log_file}】！")
        return

    print("📂 成功讀取資料庫，正在同步清理 signal_history.csv 舊世代資料...")
    df_raw = pd.read_csv(log_file, encoding="utf-8-sig", on_bad_lines="skip")
    df_raw.columns = [c.strip() for c in df_raw.columns]

    required_cols = ["日期時間", "股票代號", "觸發價格"]
    for col in required_cols:
        if col not in df_raw.columns:
            print(f"❌ 錯誤：缺少必要欄位【{col}】！")
            return

    # 1. 清理代號後綴與異常價格
    df_raw["股票代號"] = df_raw["股票代號"].astype(str).str.strip().str.split(".").str[0].str.strip()
    df_raw["觸發價格"] = pd.to_numeric(df_raw["觸發價格"], errors="coerce")
    df_raw["_dt"] = pd.to_datetime(df_raw["日期時間"], errors="coerce")
    df_raw = df_raw.dropna(subset=["_dt", "觸發價格", "股票代號"])
    df_raw = df_raw[df_raw["觸發價格"] > 0].sort_values("_dt", ascending=True).reset_index(drop=True)

    # 2. 剔除 2026-09-01 以前之舊版格式資料，並控制於 MAX_RETENTION_DAYS (90天) 內
    if not df_raw.empty:
        epoch_dt = pd.to_datetime(STABLE_EPOCH_DATE).date()
        rolling_dt = (df_raw["_dt"].max() - pd.Timedelta(days=MAX_RETENTION_DAYS)).date()
        cutoff_date = max(epoch_dt, rolling_dt)
        df_raw = df_raw[df_raw["_dt"].dt.date >= cutoff_date].copy()

    # 3. 剔除早期舊名稱「量能爆發突破」（保留新制五大訊號），並將乾淨資料存回 signal_history.csv！
    if "核心訊號" in df_raw.columns:
        valid_sig_mask = df_raw["核心訊號"].astype(str).str.contains("強勢突破|大戶惜售|出貨陷阱|深水區潛龍|底背離|背離", regex=True)
        df_raw = df_raw[valid_sig_mask].copy()

    # 🌟 同步瘦身覆寫 signal_history.csv（保留每日連續鎖碼偵測紀錄，但徹底清除 5~8 月肥大舊資料）
    df_log_clean = df_raw.drop(columns=["_dt"], errors="ignore").reset_index(drop=True)
    df_log_clean.to_csv(log_file, index=False, encoding="utf-8-sig")
    print(f"🧹 [原始日誌瘦身完成] 已更新【{log_file}】，目前保留 {len(df_log_clean)} 筆新制純淨紀錄！")

    # 4. 針對回測報表執行「同股 5 日冷卻去重」(僅對第一根起漲買點進行回測勝率統計)
    df = df_raw.copy().reset_index(drop=True)
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
    for col in period_map.keys():
        df[col] = np.nan

    total_signals = len(df)
    print(f"🎬 開始執行多週期績效回補，總計 {total_signals} 筆獨立起漲訊號...\n")

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
                    temp_data = yf.download(ticker_id, period="6mo", progress=False)
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
            # 剛觸發尚未經過隔日 (T+1) 收盤之訊號，待下個交易日收盤後自動納入結算
            continue

        valid_rows.append(idx)
        for col_name, day_offset in period_map.items():
            if len(future_data) >= day_offset:
                target_close = float(future_data["Close"].iloc[day_offset - 1])
                df.at[idx, col_name] = round(((target_close - trigger_price) / trigger_price) * 100, 2)

        print(f" 🟩 [{idx+1}/{total_signals}] 股票 {pure_sid} | 觸發日: {trigger_date} | 回補完成")

    df_clean = df.loc[valid_rows].drop(columns=["_dt"], errors="ignore").reset_index(drop=True)
    df_clean.to_csv(output_file, index=False, encoding="utf-8-sig")
    print(f"\n🎉 雙檔清理與回補大成功！已更新回測報表：【{output_file}】（共 {len(df_clean)} 筆已結算訊號）")

if __name__ == "__main__":
    run_radar_backtest()
