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

def compute_indicators(df):
  """計算 KD、MACD、RSI 與 5日均量，供歷史金星回推使用"""
  df = df.copy()
  df["Volume"] = df["Volume"] / 1000.0
  df["Vol_MA5"] = df["Volume"].rolling(5).mean()

  exp1 = df["Close"].ewm(span=12, adjust=False).mean()
  exp2 = df["Close"].ewm(span=26, adjust=False).mean()
  df["DIF"] = exp1 - exp2
  df["DEA"] = df["DIF"].ewm(span=9, adjust=False).mean()
  df["MACD_Hist"] = df["DIF"] - df["DEA"]

  low_9 = df["Low"].rolling(9).min()
  high_9 = df["High"].rolling(9).max()
  denom_kd = (high_9 - low_9).replace(0, 1)
  rsv = 100 * ((df["Close"] - low_9) / denom_kd)
  df["K"] = rsv.ewm(com=2, adjust=False).mean()
  df["D"] = df["K"].ewm(com=2, adjust=False).mean()

  delta = df["Close"].diff()
  gain = (delta.where(delta > 0, 0)).rolling(14).mean()
  loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
  rs = gain / loss.replace(0, 0.00001)
  df["RSI"] = 100 - (100 / (1 + rs))
  return df


def backfill_historical_stars(df_raw, history_cache):
  """🌟 時光機引擎：自動掃描自選股過去 60 天內的『⭐ 多指標共振金星』並補入歷史資料庫"""
  wl = DEFAULT_WATCHLIST.copy()
  if os.path.exists("watchlist.json"):
    try:
      with open("watchlist.json", "r", encoding="utf-8") as f:
        loaded_wl = json.load(f)
        if isinstance(loaded_wl, dict) and loaded_wl:
          for k, v in loaded_wl.items():
            clean_k = str(k).split(".")[0].strip()
            pure_v = (
                str(v)
                .replace(clean_k, "")
                .replace("(", "")
                .replace(")", "")
                .strip()
            )
            wl[clean_k] = pure_v
    except Exception:
      pass

  existing_stars = set()
  if not df_raw.empty and "核心訊號" in df_raw.columns:
    star_rows = df_raw[
        df_raw["核心訊號"]
        .astype(str)
        .str.contains("多指標共振|金星", regex=True)
    ]
    for _, r in star_rows.iterrows():
      existing_stars.add((str(r["股票代號"]).strip(), r["_dt"].date()))

  print(
      f"🌟 [金星時光機啟動] 正在回推 {len(wl)} 檔核心自選股自"
      f" {STABLE_EPOCH_DATE} 以來的歷史金星買點..."
  )
  epoch_dt = pd.to_datetime(STABLE_EPOCH_DATE).date()
  new_star_records = []

  for sid, sname in wl.items():
    pure_sid = str(sid).split(".")[0].strip()
    suffixes = (
        [".TWO", ".TW"]
        if pure_sid in ["3595", "7853", "3081"] or len(pure_sid) == 6
        else [".TW", ".TWO"]
    )
    stock_data = pd.DataFrame()

    for sfx in suffixes:
      try:
        tmp = yf.download(f"{pure_sid}{sfx}", period="6mo", progress=False)
        if tmp is not None and not tmp.empty and len(tmp) > 30:
          if isinstance(tmp.columns, pd.MultiIndex):
            tmp.columns = tmp.columns.get_level_values(0)
          tmp = tmp.dropna(subset=["Close"])
          tmp = tmp[(tmp["Volume"] > 0) & (tmp["Volume"].notna())]
          stock_data = tmp
          history_cache[pure_sid] = stock_data.copy()
          break
      except Exception:
        continue
    time.sleep(0.08)

    if stock_data.empty or len(stock_data) < 30:
      continue

    df_ind = compute_indicators(stock_data)

    # 嚴格零未來函數 (No Look-ahead Bias)：只用當日與前一日指標判定金星共振
    macd_gold = (df_ind["DIF"] > df_ind["DEA"]) & (
        df_ind["DIF"].shift(1) <= df_ind["DEA"].shift(1)
    )
    kd_gold = (df_ind["K"] > df_ind["D"]) & (
        df_ind["K"].shift(1) <= df_ind["D"].shift(1)
    )
    vol_burst = (df_ind["Close"] > df_ind["Open"]) & (
        df_ind["Volume"] >= df_ind["Vol_MA5"] * 1.15
    )

    macd_gold_near = macd_gold | macd_gold.shift(1, fill_value=False)
    kd_gold_near = kd_gold | kd_gold.shift(1, fill_value=False)

    bull_res = (
        kd_gold
        & (
            macd_gold_near
            | (vol_burst & (df_ind["MACD_Hist"] > df_ind["MACD_Hist"].shift(1)))
        )
    ) | (macd_gold & kd_gold_near)

    res_days = df_ind[bull_res]
    for idx_ts, row_k in res_days.iterrows():
      k_date = idx_ts.date()
      if k_date < epoch_dt or (pure_sid, k_date) in existing_stars:
        continue

      close_p = round(float(row_k["Close"]), 2)
      rsi_v = round(float(row_k["RSI"]), 2) if pd.notna(row_k["RSI"]) else 50.0
      vol_v = round(float(row_k["Volume"]), 1)
      vma5_v = (
          round(float(row_k["Vol_MA5"]), 1)
          if pd.notna(row_k["Vol_MA5"]) and row_k["Vol_MA5"] > 0
          else vol_v
      )
      v_ratio = round(vol_v / vma5_v, 2) if vma5_v > 0 else 1.0

      dt_str = f"{k_date.strftime('%Y-%m-%d')} 13:30:00"
      desc_str = (
          "🔥 綜合火力評分：85.0 分 |  | 🔗 [點擊前往 Yahoo 股市查看"
          f" {sname}](https://tw.stock.yahoo.com/quote/{pure_sid}) |  |"
          " 表面型態：⭐【多指標共振】KD+MACD 同步轉強買點！"
      )
      tech_str = (
          f"RSI 指標：{rsi_v} | 成交量比：{v_ratio}x ({vol_v}張/{vma5_v}張)"
      )

      new_star_records.append({
          "日期時間": dt_str,
          "股票代號": pure_sid,
          "股票名稱": sname,
          "觸發價格": close_p,
          "核心訊號": desc_str,
          "技術與量能": tech_str,
          "_dt": pd.to_datetime(dt_str),
      })
      existing_stars.add((pure_sid, k_date))

  if new_star_records:
    df_stars = pd.DataFrame(new_star_records)
    print(
        f"✨ [金星回推大豐收] 成功挖掘出 {len(df_stars)} 筆歷史『⭐"
        " 多指標共振』買點並併入資料庫！"
    )
    df_combined = (
        pd.concat([df_raw, df_stars], ignore_index=True)
        .sort_values("_dt", ascending=True)
        .reset_index(drop=True)
    )
    return df_combined
  else:
    print("ℹ️ [金星回推完成] 資料庫已包含最新金星紀錄，無須重複新增。")
    return df_raw

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
  df_raw["股票代號"] = (
      df_raw["股票代號"].astype(str).str.strip().str.split(".").str[0].str.strip()
  )
  df_raw["觸發價格"] = pd.to_numeric(df_raw["觸發價格"], errors="coerce")
  df_raw["_dt"] = pd.to_datetime(df_raw["日期時間"], errors="coerce")
  df_raw = df_raw.dropna(subset=["_dt", "觸發價格", "股票代號"])
  df_raw = (
      df_raw[df_raw["觸發價格"] > 0]
      .sort_values("_dt", ascending=True)
      .reset_index(drop=True)
  )

  # 2. 剔除 2026-09-01 以前之舊版格式資料，並控制於 MAX_RETENTION_DAYS (90天) 內
  if not df_raw.empty:
    epoch_dt = pd.to_datetime(STABLE_EPOCH_DATE).date()
    rolling_dt = (
        df_raw["_dt"].max() - pd.Timedelta(days=MAX_RETENTION_DAYS)
    ).date()
    cutoff_date = max(epoch_dt, rolling_dt)
    df_raw = df_raw[df_raw["_dt"].dt.date >= cutoff_date].copy()

  # 3. 保留新制六大訊號（含 ⭐ 多指標共振）
  if "核心訊號" in df_raw.columns:
    valid_sig_mask = (
        df_raw["核心訊號"]
        .astype(str)
        .str.contains(
            "強勢突破|大戶惜售|出貨陷阱|深水區潛龍|底背離|背離|多指標共振|金星",
            regex=True,
        )
    )
    df_raw = df_raw[valid_sig_mask].copy()

  # 🌟 3.5 啟動時光機：自動回推 50 檔核心自選股的歷史金星買點，並共用 history_cache 加速後續回補！
  history_cache = {}
  df_raw = backfill_historical_stars(df_raw, history_cache)

  # 🌟 同步瘦身覆寫 signal_history.csv
  df_log_clean = df_raw.drop(columns=["_dt"], errors="ignore").reset_index(
      drop=True
  )
  df_log_clean.to_csv(log_file, index=False, encoding="utf-8-sig")
  print(
      f"🧹 [原始日誌更新完成] 已寫入【{log_file}】，目前保留"
      f" {len(df_log_clean)} 筆新制純淨紀錄！"
  )

  # 4. 針對回測報表執行「同股同訊號 5 日冷卻去重」
  def _clean_sig_tag(x):
    s = str(x)
    if "多指標共振" in s or "金星" in s:
      return "STAR"
    if "強勢突破" in s:
      return "BREAK"
    if "大戶惜售" in s:
      return "HOLD"
    if "出貨陷阱" in s:
      return "TRAP"
    if "深水區潛龍" in s:
      return "DRAGON"
    if "底背離" in s or "背離" in s:
      return "DIV"
    return "OTHER"

  df = df_raw.copy().reset_index(drop=True)
  kept_indices = []
  last_trigger = {}
  for idx, row in df.iterrows():
    sid = row["股票代號"]
    sig_tag = _clean_sig_tag(row.get("核心訊號", ""))
    t_date = row["_dt"].date()
    key_pair = (sid, sig_tag)
    if (
        key_pair not in last_trigger
        or (t_date - last_trigger[key_pair]).days >= COOLDOWN_DAYS
    ):
      kept_indices.append(idx)
      last_trigger[key_pair] = t_date
  df = df.loc[kept_indices].reset_index(drop=True)

  period_map = {
      "T+1 報酬率(%)": 1,
      "T+3 報酬率(%)": 3,
      "T+5 報酬率(%)": 5,
      "T+10 報酬率(%)": 10,
      "T+20 報酬率(%)": 20,
  }
  for col in period_map.keys():
    df[col] = np.nan

  total_signals = len(df)
  print(
      f"🎬 開始執行多週期績效回補，總計 {total_signals} 筆獨立起漲訊號...\n"
  )

  valid_rows = []

  for idx, row in df.iterrows():
    pure_sid = str(row["股票代號"]).strip()
    trigger_price = float(row["觸發價格"])
    trigger_date = row["_dt"].date()

    suffixes = (
        [".TWO", ".TW"]
        if pure_sid in ["3595", "7853", "3081"] or len(pure_sid) == 6
        else [".TW", ".TWO"]
    )
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
        df.at[idx, col_name] = round(
            ((target_close - trigger_price) / trigger_price) * 100, 2
        )

    print(
        f"  🟩 [{idx+1}/{total_signals}] 股票 {pure_sid} | 觸發日:"
        f" {trigger_date} | 回補完成"
    )

  df_clean = (
      df.loc[valid_rows]
      .drop(columns=["_dt"], errors="ignore")
      .reset_index(drop=True)
  )
  df_clean.to_csv(output_file, index=False, encoding="utf-8-sig")
  print(
      "\n🎉 雙檔清理、金星回推與回補大成功！已更新回測報表："
      f"【{output_file}】（共 {len(df_clean)} 筆已結算訊號）"
  )


if __name__ == "__main__":
  run_radar_backtest()
