秉諺的股票機器人指令手冊 (V7.8)
1. 環境建置 (第一次使用或報錯時執行)
如果你換了電腦，或是執行時出現 `ModuleNotFoundError`，請在 CMD 輸入： `python -m pip install streamlit yfinance pandas plotly requests`

2. 日常啟動指令
請先確認 CMD 路徑已切換至資料夾： `cd Desktop\stock_lab`

• 啟動網頁儀表板 (看 K 線、法說資訊)： `streamlit run app.py`

• 執行自動掃描器 (發送 Discord 通知)： `python auto_scan.py`

3. 維護與更新
• 檢查已安裝套件： `pip list`

• 更新股價抓取組件 (若抓不到資料時執行)： `pip install --upgrade yfinance`

4. 自動化小撇步 (建立 .bat 檔)
在桌面建立一個記事本，貼入以下內容並另存為 `啟動掃描.bat`：

```

@echo off

cd /d C:\Users\user\Desktop\stock_lab

python auto_scan.py

pause

```
網址:https://jimjimwu-stock.streamlit.app/
