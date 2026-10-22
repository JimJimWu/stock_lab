# 🐎 秉諺的黑馬雷達 (BlackHorse Radar) V43.0

「黑馬雷達」是一款基於 Python 與 Streamlit 開發的高頻量化看盤與決策輔助系統。整合了 Yahoo Finance 實時數據、Google Gemini AI 產業分析、多週期勝率回測引擎，以及 Discord 背景自動推播功能，專為台股實戰量身打造。

## ✨ 核心架構與最新亮點

*   **☁️ 終極雲端資料庫 (V43.0)**：結合 Google Sheets API，實現 `watchlist.json` (自選股) 與 `industry_db.json` (AI 產業百科) 的雙向智慧合併與永久雲端保存，徹底解決雲端部署的檔案重置問題。
*   **📈 策略多週期勝率分析儀 (V42.2)**：內建「連續鎖碼偵測中心」與「T+1 ~ T+20 多週期勝率交叉圖」，利用歷史大數據視覺化呈現各類訊號的真實勝率。
*   **🛠️ 自體季報反算引擎 (V42.1)**：獨創黑科技防禦網，自動修補 Yahoo Finance 對於台灣中小型股 (OTC) 及大型權值股 (如台積電) 經常缺失的 EPS、ROE 與 PE 數據，直接調閱原始財報進行反算。
*   **🤖 AI 戰略官與百科生成器 (V42.0)**：導入 Gemini 2.5 Flash 大語言模型，一鍵自動連網檢索並生成結構化產業百科，並提供即時多空位階與 3-3-4 建倉紀律推演。
*   **🚨 全方位火力評分與推播 (V41.0)**：兼容量能爆發與量縮惜售邏輯，背景執行 `auto_scan.py` 自動過濾全市場，將達標精華推播至 Discord。

## 📂 專案檔案結構

*   `app.py`：Streamlit 網頁前端主程式（包含視覺化看板、AI 百科、雲端控制台）。
*   `auto_scan.py`：背景自動無人值守掃描器（支援 crontab 排程），負責全市場過濾與 Discord 告警。
*   `backtest_processor.py`：量化回測未來績效自動回補引擎，計算 T+1 至 T+20 的真實報酬率。
*   `watchlist.json`：本地自選股清單（會與雲端自動同步）。
*   `industry_db.json`：本地 AI 產業百科資料庫（會與雲端自動同步）。
*   `signal_history.csv`：雷達觸發訊號的原始歷史日誌。
*   `signal_history_backtest.csv`：經過回測引擎處理後，帶有未來績效的分析報表。

## ⚙️ 系統部署與環境設定

1.  **安裝依賴套件**：
    ```bash
    pip install streamlit pandas yfinance plotly google-generativeai gspread oauth2client
    ```
2.  **Streamlit Cloud Secrets 設定**：
    在部署環境中，必須設定以下環境變數 (Secrets)：
    *   `GEMINI_API_KEY`：Google Gemini API 金鑰。
    *   `DISCORD_WEBHOOK`：Discord 頻道的 Webhook URL。
    *   `SHEET_URL`：Google Sheets 試算表的完整網址。
    *   `GSPREAD_JSON`：Google Cloud Service Account 的 JSON 憑證內容。
3.  **啟動系統**：
    ```bash
    streamlit run app.py
    ```