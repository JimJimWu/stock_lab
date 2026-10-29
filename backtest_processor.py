# ==============================================================================
# 🐎 黑馬雷達專用：量化回測未來績效自動回補引擎 (V7.0 機構級資料清洗與真實勝率版)
# ==============================================================================
import pandas as pd
import numpy as np
import yfinance as yf
import datetime
import os
import time

# ==============================================================================
# ⚙️ 【回測清洗與實戰結算參數設定區】(可依需求自由調整)
# ==============================================================================
# 1. 策略世代切割日：剔除此日期之前的早期舊版條件資料 (設為 None 則保留全部歷史)
EPOCH_START_DATE = "2026-01-01"

# 2. 同股冷卻期去重天數：同一檔股票在 N 天內重複觸發時，僅保留第 1 筆起漲訊號 (設為 0 則不去重)
COOLDOWN_DAYS = 5

# 3. 實戰觸價停利鎖定：若持有週期內最高價(High)已達停利目標(如 +8%)，是否鎖定獲利防止回吐誤判為敗場
ENABLE_TAKE_PROFIT_LOCK = True
TAKE_PROFIT_TARGET_PCT = 8.0   # 盤中觸及 +8.0% 視為波段停利達標
STOP_LOSS_LIMIT_PCT = -4.0     # 若先跌破 -4.0% 則視為觸發停損
# ==============================================================================

def clean_and_deduplicate_signals(df):
    """
    執行三階段歷史資料清洗：
    1. 正規化纯數字股號與有效觸發價格
    2. 策略世代日期切割 (剔除舊世代不完整條件之紀錄)
    3. 同股 N 日冷卻期去重 (剔除連續日重複追高雜訊)
    """
    raw_len = len(df)

    # 正規化股號：徹底消除 .TW.TW、.TW、.TWO 與空白
    df["股票代號_純數字"] = (
        df["股票代號"]
        .astype(str)
        .str.strip()
        .str.split(".")
        .str[0]
        .str.strip()
    )

    # 轉換價格與日期，剔除價格 <= 0 或日期格式損壞之無效列
    df["觸發價格"] = pd.to_numeric(df["觸發價格"], errors="coerce")
    df["_parsed_dt"] = pd.to_datetime(df["日期時間"], errors="coerce")
    df = df.dropna(subset=["觸發價格", "_parsed_dt", "股票代號_純數字"])
    df = df[df["觸發價格"] > 0].copy()

    # 依觸發時間由舊到新排序
    df = df.sort_values(by="_parsed_dt", ascending=True).reset_index(drop=True)

    # 階段 1：策略世代切割
    if EPOCH_START_DATE:
        cutoff_dt = pd.to_datetime(EPOCH_START_DATE).date()
        df = df[df["_parsed_dt"].dt.date >= cutoff_dt].copy()
        print(f"🧹 [世代切割] 已剔除 {EPOCH_START_DATE} 前之舊資料，剩餘 {len(df)} 筆。")

    # 階段 2：同股 N 日冷卻期去重
    if COOLDOWN_DAYS and COOLDOWN_DAYS > 0:
        kept_indices = []
        last_trigger_map = {}
        for idx, row in df.iterrows():
            sid = row["股票代號_純數字"]
            trig_date = row["_parsed_dt"].date()
            if sid not in last_trigger_map or (trig_date - last_trigger_map[sid]).days >= COOLDOWN_DAYS:
                kept_indices.append(idx)
                last_trigger_map[sid] = trig_date
        df = df.loc[kept_indices].copy()
        print(f"🧹 [冷卻去重] 啟用 {COOLDOWN_DAYS} 日同股去重後，由 {raw_len} 筆濃縮為 {len(df)} 筆純淨起漲訊號。")

    return df.reset_index(drop=True)


def run_radar_backtest():
    log_file = "signal_history.csv"
    output_file = "signal_history_backtest.csv"

    if not os.path.exists(log_file):
        print(f"❌ 錯誤：找不到來源檔案【{log_file}】！")
        return

    print("📂 成功讀取資料庫，正在載入並清洗訊號紀錄...")
    df = pd.read_csv(log_file, encoding="utf-8-sig", on_bad_lines="skip")
    df.columns = [c.strip() for c in df.columns]

    required_cols = ["日期時間", "股票代號", "觸發價格"]
    for col in required_cols:
        if col not in df.columns:
            print(f"❌ 錯誤：缺少必要欄位【{col}】！")
            return

    # 執行歷史資料清洗與同股冷卻去重
    df = clean_and_deduplicate_signals(df)
    if df.empty:
        print("⚠️ 清洗後無符合條件之訊號紀錄。")
        return

    period_map = {
        "T+1 報酬率(%)": 1,
        "T+3 報酬率(%)": 3,
        "T+5 報酬率(%)": 5,
        "T+10 報酬率(%)": 10,
        "T+20 報酬率(%)": 20
    }

    # 🌟 關鍵修正 1：一律初始化為 np.nan (空值)，嚴禁填 0.0 造成未到期訊號被誤判為敗場！
    for col in period_map.keys():
        df[col] = np.nan
    df["20日最大潛力漲幅(%)"] = np.nan

    total_signals = len(df)
    print(f"🎬 開始執行多週期量化績效回補，總計 {total_signals} 筆純淨訊號...\n")

    history_cache = {}
    valid_row_indices = []

    for idx, row in df.iterrows():
        raw_sid = str(row["股票代號"]).strip()
        pure_sid = str(row["股票代號_純數字"]).strip()
        trigger_price = float(row["觸發價格"])
        trigger_date = row["_parsed_dt"].date()

        # 🌟 關鍵修正 2：徹底根除 .TW.TW 雙重後綴問題，永遠由純數字 pure_sid 組裝候選清單
        prefer_two = (".TWO" in raw_sid.upper()) or (pure_sid in ["3595", "7853", "3081"]) or (len(pure_sid) == 6)
        if prefer_two:
            candidate_tickers = [f"{pure_sid}.TWO", f"{pure_sid}.TW"]
        else:
            candidate_tickers = [f"{pure_sid}.TW", f"{pure_sid}.TWO"]

        # 將乾淨的純代號寫回欄位
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
            time.sleep(0.12)

        if stock_data.empty:
            print(f" ⚠️ [{idx+1}/{total_signals}] 股票 {pure_sid} | 查無歷史數據，予以剔除。")
            continue

        future_data = stock_data[stock_data.index.date > trigger_date]
        if future_data.empty:
            print(f" ⏳ [{idx+1}/{total_signals}] 股票 {pure_sid} | 觸發日: {trigger_date} | 訊號剛觸發尚無 T+1 收盤數據，暫不列入結算。")
            continue

        valid_row_indices.append(idx)

        # 計算 20 日內盤中最高價潛力漲幅 (Maximum Favorable Excursion)
        window_20 = future_data.iloc[:20]
        if "High" in window_20.columns and not window_20["High"].dropna().empty:
            max_high_20 = float(window_20["High"].max())
            df.at[idx, "20日最大潛力漲幅(%)"] = round(((max_high_20 - trigger_price) / trigger_price) * 100, 2)

        # 計算各持有週期報酬率
        for col_name, day_offset in period_map.items():
            if len(future_data) >= day_offset:
                sub_window = future_data.iloc[:day_offset]
                target_close = float(sub_window["Close"].iloc[-1])
                close_ret_pct = round(((target_close - trigger_price) / trigger_price) * 100, 2)

                # 🌟 關鍵修正 3：實戰觸價停利鎖定邏輯 (避免盤中已大賺停利、收盤洗盤回吐被誤記為虧損)
                if ENABLE_TAKE_PROFIT_LOCK and "High" in sub_window.columns and "Low" in sub_window.columns:
                    final_ret = close_ret_pct
                    for _, k_row in sub_window.iterrows():
                        day_low_pct = ((float(k_row["Low"]) - trigger_price) / trigger_price) * 100.0
                        day_high_pct = ((float(k_row["High"]) - trigger_price) / trigger_price) * 100.0
                        if day_low_pct <= STOP_LOSS_LIMIT_PCT:
                            final_ret = round(STOP_LOSS_LIMIT_PCT, 2)
                            break
                        if day_high_pct >= TAKE_PROFIT_TARGET_PCT:
                            final_ret = round(max(close_ret_pct, TAKE_PROFIT_TARGET_PCT), 2)
                            break
                    df.at[idx, col_name] = final_ret
                else:
                    df.at[idx, col_name] = close_ret_pct

        print(f" 🟩 [{idx+1}/{total_signals}] 股票 {pure_sid} | 觸發日: {trigger_date} | 多週期回補完成")

    # 僅保留至少具備 T+1 數據的有效結算列，並移除內部暫存欄位
    df_final = df.loc[valid_row_indices].drop(columns=["股票代號_純數字", "_parsed_dt"], errors="ignore").reset_index(drop=True)
    df_final.to_csv(output_file, index=False, encoding="utf-8-sig")

    # 輸出終端機即時勝率診斷摘要
    print(f"\n🎉 量化多週期績效回補大成功！已輸出純淨回測報表：【{output_file}】（共 {len(df_final)} 筆有效結算訊號）")
    print("=" * 65)
    for col_name in period_map.keys():
        valid_s = df_final[col_name].dropna()
        if len(valid_s) > 0:
            win_cnt = (valid_s > 0).sum()
            wr = round((win_cnt / len(valid_s)) * 100, 1)
            avg_r = round(valid_s.mean(), 2)
            print(f" 📊 {col_name:<12} | 已到期樣本: {len(valid_s):>4} 筆 | 勝率: {wr:>5}% | 平均報酬: {avg_r:>6}%")
    print("=" * 65)

if __name__ == "__main__":
    run_radar_backtest()
