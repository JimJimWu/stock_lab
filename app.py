import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import json
import os

# --- 1. 基本設定 ---
st.set_page_config(layout="wide", page_title="秉諺的黑馬雷達 V16.2")

# 新增標的後的清單
STOCK_DICT = {
    "3595": "3595 (山太士)", "3450": "3450 (聯鈞)", "3037": "3037 (欣興)", 
    "2330": "2330 (台積電)", "3363": "3363 (上詮)", "6451": "6451 (訊芯-KY)", 
    "3163": "3163 (波若威)", "4979": "4979 (華星光)", "3081": "3081 (聯亞)", 
    "2455": "2455 (全新)", "6442": "6442 (光聖)",
    "2486": "2486 (一銓)", "3714": "3714 (富采)", "1802": "1802 (台玻)",
    "2408": "2408 (南亞科)", "1815": "1815 (富喬)", "4958": "4958 (臻鼎-KY)"
}

# --- 2. 數據核心 (穩定抓取) ---
@st.cache_data(ttl=3600)
def get_analysis_data(sid):
    for suffix in [".TW", ".TWO"]:
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
                df['MA5'] = df['Close'].rolling(5).mean(); df['MA10'] = df['Close'].rolling(10).mean(); df['MA20'] = df['Close'].rolling(20).mean()
                exp1, exp2 = df['Close'].ewm(span=12).mean(), df['Close'].ewm(span=26).mean()
                df['DIF'] = exp1 - exp2; df['DEA'] = df['DIF'].ewm(span=9).mean(); df['MACD_Hist'] = df['DIF'] - df['DEA']
                low_9, high_9 = df['Low'].rolling(9).min(), df['High'].rolling(9).max()
                rsv = 100 * ((df['Close'] - low_9) / (high_9 - low_9))
                df['K'], df['D'] = rsv.ewm(com=2).mean(), rsv.ewm(com=2).mean().ewm(com=2).mean()
                delta = df['Close'].diff(); gain, loss = (delta.where(delta > 0, 0)).rolling(14).mean(), (-delta.where(delta < 0, 0)).rolling(14).mean()
                df['RSI'] = (100 - (100 / (1 + gain/loss)))
                return df, full_symbol
        except: continue
    return pd.DataFrame(), None

# --- 3. 產業百科資料 (新增標的相關資訊) ---
INDUSTRY_DB = {
    "散熱與導線架": {"stocks": ["2486"], "overview": "隨AI伺服器需求，均熱片與散熱模組成為核心，市場年成長約10-15%。", "value_chain": "上游：銅材 -> 中游：一銓(導線架/均熱片) -> 下游：伺服器組裝。"},
    "LED 與 化合物半導體": {"stocks": ["3714", "3595"], "overview": "Micro LED 與 Mini LED 為次世代顯示主流。", "value_chain": "磊晶(富采) -> 封裝(山太士) -> 終端顯示。"},
    "傳統與電子玻璃": {"stocks": ["1802", "1815"], "overview": "玻纖布為PCB關鍵基礎材料，AI需求帶動高階低損耗材料。", "value_chain": "玻纖紗 -> 玻纖布(富喬) -> CCL銅箔基板 -> PCB。"},
    "記憶體 (DRAM)": {"stocks": ["2408"], "overview": "全球記憶體景氣循環明顯，HBM 與 DDR5 為目前高價利潤區。", "value_chain": "設計/製造(南亞科) -> 封測 -> 消費電子/雲端中心。"},
    "高階載板與 PCB": {"stocks": ["3037", "4958"], "overview": "台灣為全球PCB產值龍頭，臻鼎與欣興為全球領先廠商。", "value_chain": "基板材料 -> 電路加工 -> 封裝載板(欣興/臻鼎)。"}
}

# --- 4. Sidebar 介面 ---
with st.sidebar:
    st.markdown(f"""<div style="background: linear-gradient(135deg, #1e3a8a, #000000); padding: 15px; border-radius: 12px; border: 1px solid #3b82f6;">
        <h1 style="color: #60a5fa; font-size: 18px; margin: 0; text-align: center;">🚀 戰情操控中心</h1>
        <p style="color: #94a3b8; font-size: 11px; text-align: center; margin-top:5px;">吳秉諺 專屬系統 V16.2</p>
    </div>""", unsafe_allow_html=True)
    selected_label = st.selectbox("🎯 選擇標的 (Target)", list(STOCK_DICT.values()))
    target_sid = selected_label.split(" ")[0]
    view_days = st.slider("📅 顯示天數", 30, 240, 90)
    
    st.sidebar.divider()
    current_ind = next((n for n, d in INDUSTRY_DB.items() if target_sid in d.get("stocks", [])), "通用電子")
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
        # --- 紅漲綠跌校正：diff >= 0 顯示紅色(normal) ---
        m_color = "normal" if diff >= 0 else "inverse"
        
        st.markdown("### 🛡️ 技術防線")
        st.metric("最新報價", f"{round(last['Close'], 2)}", f"{diff}", delta_color=m_color)
        st.write(f"**MA5：** :orange[{round(last['MA5'], 2)}]"); st.write(f"**MA10：** :blue[{round(last['MA10'], 2)}]"); st.write(f"**MA20：** :violet[{round(last['MA20'], 2)}]")
        
        if a_data:
            st.divider()
            st.subheader("📊 財務表現")
            st.write(f"**ROE：** :blue[{a_data['ROE']}]")
            st.write(f"**本益比：** `{a_data['本益比']}`")
            st.write(f"**法人持股：** `{round(a_data['法人持股'], 1)}%`")
            st.write(f"**營收成長：** `{round(a_data['營收成長率']*100, 1)}%` {'✅' if a_data['營收成長率']>0 else '🔴'}")

with col_main:
    if not df.empty:
        plot_df = df.tail(view_days)
        # --- 紅漲綠跌繪圖 ---
        fig = make_subplots(rows=4, cols=1, shared_xaxes=True, vertical_spacing=0.04, row_heights=[0.4, 0.1, 0.2, 0.2])
        fig.add_trace(go.Candlestick(x=plot_df.index, open=plot_df['Open'], high=plot_df['High'], low=plot_df['Low'], close=plot_df['Close'], 
                                     decreasing=dict(fillcolor='green', line=dict(color='green')), 
                                     increasing=dict(fillcolor='red', line=dict(color='red'))), row=1, col=1)
        fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df['MA10'], name="10MA", line=dict(color='#60a5fa')), row=1, col=1)
        fig.add_trace(go.Bar(x=plot_df.index, y=plot_df['Volume'], name="成交量", marker_color='#334155'), row=2, col=1)
        fig.add_trace(go.Bar(x=plot_df.index, y=plot_df['MACD_Hist'], name="MACD"), row=3, col=1)
        fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df['K'], name="K", line=dict(color='white')), row=4, col=1)
        fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df['D'], name="D", line=dict(color='yellow')), row=4, col=1)
        fig.update_layout(height=1000, template="plotly_dark", xaxis_rangeslider_visible=False)
        st.plotly_chart(fig, use_container_width=True)