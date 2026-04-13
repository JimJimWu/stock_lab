import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import json
import os

# --- 1. 基本設定 ---
st.set_page_config(layout="wide", page_title="秉諺的黑馬雷達 V16.4")

# 完整標的清單 (17 檔)
STOCK_DICT = {
    "3595": "3595 (山太士)", "3450": "3450 (聯鈞)", "3037": "3037 (欣興)", 
    "2330": "2330 (台積電)", "3363": "3363 (上詮)", "6451": "6451 (訊芯-KY)", 
    "3163": "3163 (波若威)", "4979": "4979 (華星光)", "3081": "3081 (聯亞)", 
    "2455": "2455 (全新)", "6442": "6442 (光聖)",
    "2486": "2486 (一銓)", "3714": "3714 (富采)", "1802": "1802 (台玻)",
    "2408": "2408 (南亞科)", "1815": "1815 (富喬)", "4958": "4958 (臻鼎-KY)"
}

# --- 2. 數據核心 (修正上市/上櫃自動判斷邏輯) ---
@st.cache_data(ttl=3600)
def get_analysis_data(sid):
    # 嘗試兩種後綴，確保 3595 等特殊標的能抓到
    for suffix in [".TWO", ".TW"]:
        try:
            ticker = yf.Ticker(f"{sid}{suffix}")
            info = ticker.info
            if info and ('regularMarketPrice' in info or 'symbol' in info):
                return {
                    "EPS": info.get("trailingEps", "N/A"),
                    "營收成長率": info.get('revenueGrowth', 0),
                    "負債比": info.get('debtToEquity', 0),
                    "ROE": f"{round(info.get('returnOnEquity', 0)*100, 2)}%" if info.get('returnOnEquity') else "N/A",
                    "本益比": round(info.get("trailingPE", 0), 2) if info.get("trailingPE") else "N/A",
                    "法人持股": info.get("heldPercentInstitutions", 0) * 100
                }
        except: continue
    return None

@st.cache_data(ttl=600)
def get_stock_df(sid):
    for suffix in [".TWO", ".TW"]:
        try:
            full_symbol = f"{sid}{suffix}"
            df = yf.Ticker(full_symbol).history(period="2y", auto_adjust=True)
            if not df.empty and len(df) > 10:
                if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
                # 技術指標計算
                df['MA5'] = df['Close'].rolling(5).mean()
                df['MA10'] = df['Close'].rolling(10).mean()
                df['MA20'] = df['Close'].rolling(20).mean()
                # MACD
                exp1, exp2 = df['Close'].ewm(span=12).mean(), df['Close'].ewm(span=26).mean()
                df['DIF'] = exp1 - exp2
                df['DEA'] = df['DIF'].ewm(span=9).mean()
                df['MACD_Hist'] = df['DIF'] - df['DEA']
                # KD
                low_9, high_9 = df['Low'].rolling(9).min(), df['High'].rolling(9).max()
                rsv = 100 * ((df['Close'] - low_9) / (high_9 - low_9))
                df['K'], df['D'] = rsv.ewm(com=2).mean(), rsv.ewm(com=2).mean().ewm(com=2).mean()
                # RSI
                delta = df['Close'].diff()
                gain, loss = (delta.where(delta > 0, 0)).rolling(14).mean(), (-delta.where(delta < 0, 0)).rolling(14).mean()
                df['RSI'] = (100 - (100 / (1 + gain/loss)))
                return df, full_symbol
        except: continue
    return pd.DataFrame(), None

# --- 3. 產業百科資料 (新增標的同步更新) ---
INDUSTRY_DB = {
    "散熱與導線架": {"stocks": ["2486"], "overview": "隨AI伺服器需求，均熱片與散熱模組成為核心。", "value_chain": "上游：銅材 -> 中游：一銓(均熱片) -> 下游：伺服器組裝。"},
    "LED與化合物半導體": {"stocks": ["3714", "3595"], "overview": "Micro/Mini LED 為次世代顯示技術。", "value_chain": "磊晶(富采) -> 封裝(山太士) -> 終端顯示。"},
    "電子玻璃與玻纖布": {"stocks": ["1802", "1815"], "overview": "玻纖布為PCB基礎材料，AI需求帶動高階材料。", "value_chain": "玻纖布(富喬) -> 銅箔基板(CCL) -> PCB。"},
    "記憶體產業": {"stocks": ["2408"], "overview": "DRAM 景氣循環回溫，HBM需求強勁。", "value_chain": "製造(南亞科) -> 封裝 -> 消費電子。"},
    "PCB與載板大廠": {"stocks": ["3037", "4958"], "overview": "AI帶動ABF載板與高階多層板需求。", "value_chain": "材料 -> 載板(欣興/臻鼎) -> 終端晶片。"}
}

# --- 4. Sidebar 介面 ---
with st.sidebar:
    st.markdown(f"""<div style="background: linear-gradient(135deg, #1e3a8a, #000000); padding: 15px; border-radius: 12px; border: 1px solid #3b82f6;">
        <h1 style="color: #60a5fa; font-size: 18px; margin: 0; text-align: center;">🚀 戰情操控中心</h1>
        <p style="color: #94a3b8; font-size: 11px; text-align: center; margin-top:5px;">吳秉諺 專屬系統 V16.4</p>
    </div>""", unsafe_allow_html=True)
    
    selected_label = st.selectbox("🎯 選擇標的 (Target)", list(STOCK_DICT.values()))
    target_sid = selected_label.split(" ")[0]
    view_days = st.slider("📅 顯示天數", 30, 240, 90)
    
    st.sidebar.divider()
    st.sidebar.link_button("🌐 Yahoo 股市", f"https://tw.stock.yahoo.com/quote/{target_sid}")
    st.sidebar.link_button("📊 Goodinfo 財報", f"https://goodinfo.tw/tw/StockDetail.asp?STOCK_ID={target_sid}")
    
    current_ind = next((n for n, d in INDUSTRY_DB.items() if target_sid in d.get("stocks", [])), "通用電子零件")
    st.sidebar.subheader(f"🏢 {current_ind} 百科")
    if current_ind in INDUSTRY_DB:
        d = INDUSTRY_DB[current_ind]
        with st.sidebar.expander("📍 市場與價值鏈", expanded=True):
            st.info(f"**概況：** {d['overview']}")
            st.info(f"**鏈條：** {d['value_chain']}")

# --- 5. 主介面 ---
df, full_symbol = get_stock_df(target_sid)
a_data = get_analysis_data(target_sid)
col_info, col_main = st.columns([1, 3])

with col_info:
    if not df.empty:
        last, prev = df.iloc[-1], df.iloc[-2]
        diff = round(last['Close'] - prev['Close'], 2)
        # --- 顏色校正：紅漲綠跌 (st.metric normal = 漲紅) ---
        m_color = "normal" if diff >= 0 else "inverse"
        
        st.markdown("### 🛡️ 技術防線")
        st.metric("最新報價", f"{round(last['Close'], 2)}", f"{diff}", delta_color=m_color)
        st.write(f"**MA5 (橘)：** :orange[{round(last['MA5'], 2)}]")
        st.write(f"**MA10 (藍)：** :blue[{round(last['MA10'], 2)}]")
        st.write(f"**MA20 (紫)：** :violet[{round(last['MA20'], 2)}]")
        
        st.divider()
        st.subheader("📈 指標診斷")
        st.write(f"**MACD：** {'🔴 死叉' if last['DIF'] < last['DEA'] else '🟢 金叉'}")
        st.write(f"**KD 狀態：** {'🔴 死叉' if last['K'] < last['D'] else '🟢 金叉'}")

        if a_data:
            st.divider()
            st.subheader("📊 財務表現 & 警示")
            rev_val, debt_val = a_data['營收成長率'], a_data['負債比']
            st.write(f"**EPS：** :green[{a_data['EPS']}]")
            st.write(f"**ROE 獲利：** :blue[{a_data['ROE']}]")
            st.write(f"**本益比 P/E：** `{a_data['本益比']}`")
            st.write(f"**營收成長：** `{round(rev_val*100, 1)}%` {'✅' if rev_val>0 else '🔴'}")
            st.write(f"**負債比率：** `{round(debt_val, 1)}%` {'✅' if debt_val<60 else '🔴'}")
            st.write(f"**法人持股：** `{round(a_data['法人持股'], 1)}%`")

with col_main:
    if not df.empty:
        plot_df = df.tail(view_days)
        rsi_val = round(plot_df['RSI'].iloc[-1], 2)
        color = "#ef4444" if rsi_val > 80 else ("#10b981" if rsi_val < 40 else "#f59e0b")
        msg = "⚠️【高檔過熱】" if rsi_val > 80 else ("✅【低檔安全】" if rsi_val < 40 else "⚖️【區間震盪】")
        
        st.markdown(f"""<div style="background: linear-gradient(90deg, #111827, #000000); border-left: 10px solid {color}; padding: 20px; border-radius: 12px;">
            <p style="color:white; font-size: 32px; font-weight: 900; margin:0;">{selected_label} <span style="font-size: 24px; color: {color};">RSI: {rsi_val}</span></p>
            <p style="color:{color}; font-size: 24px; font-weight: bold; margin-top: 10px;">{msg}</p>
        </div>""", unsafe_allow_html=True)

        fig = make_subplots(rows=4, cols=1, shared_xaxes=True, vertical_spacing=0.04, 
                           row_heights=[0.4, 0.1, 0.2, 0.2],
                           subplot_titles=("價格與均線", "成交量", "MACD 趨勢", "KD 震盪圖"))
        
        # 1. K線 (紅漲綠跌)
        fig.add_trace(go.Candlestick(x=plot_df.index, open=plot_df['Open'], high=plot_df['High'], low=plot_df['Low'], close=plot_df['Close'], 
                                     name="K線", decreasing=dict(fillcolor='green', line=dict(color='green')), 
                                     increasing=dict(fillcolor='red', line=dict(color='red'))), row=1, col=1)
        fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df['MA5'], name="5MA", line=dict(color='orange')), row=1, col=1)
        fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df['MA10'], name="10MA", line=dict(color='#60a5fa')), row=1, col=1)
        fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df['MA20'], name="20MA", line=dict(color='violet')), row=1, col=1)
        
        # 2. 成交量
        fig.add_trace(go.Bar(x=plot_df.index, y=plot_df['Volume'], name="成交量", marker_color='#334155'), row=2, col=1)
        
        # 3. MACD (補回紅綠柱狀圖)
        colors = ['red' if x > 0 else 'green' for x in plot_df['MACD_Hist']]
        fig.add_trace(go.Bar(x=plot_df.index, y=plot_df['MACD_Hist'], name="MACD柱", marker_color=colors), row=3, col=1)
        fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df['DIF'], name="DIF", line=dict(color='cyan')), row=3, col=1)
        fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df['DEA'], name="DEA", line=dict(color='yellow')), row=3, col=1)
        
        # 4. KD
        fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df['K'], name="K", line=dict(color='white')), row=4, col=1)
        fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df['D'], name="D", line=dict(color='yellow')), row=4, col=1)
        
        fig.update_layout(height=1000, template="plotly_dark", xaxis_rangeslider_visible=False, showlegend=False)
        st.plotly_chart(fig, use_container_width=True)