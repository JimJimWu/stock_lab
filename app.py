import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import requests
import json
import os
from datetime import datetime

# --- 1. 基本設定 ---
st.set_page_config(layout="wide", page_title="秉諺的黑馬雷達 V16.8")

# 完整標的清單 (17 檔)
STOCK_DICT = {
    "3595": "3595 (山太士)", "3450": "3450 (聯鈞)", "3037": "3037 (欣興)", 
    "2330": "2330 (台積電)", "3363": "3363 (上詮)", "6451": "6451 (訊芯-KY)", 
    "3163": "3163 (波若威)", "4979": "4979 (華星光)", "3081": "3081 (聯亞)", 
    "2455": "2455 (全新)", "6442": "6442 (光聖)",
    "2486": "2486 (一銓)", "3714": "3714 (富采)", "1802": "1802 (台玻)",
    "2408": "2408 (南亞科)", "1815": "1815 (富喬)", "4958": "4958 (臻鼎-KY)"
}

# --- 2. 產業百科資料 (包含競爭格局與驅動因子) ---
INDUSTRY_DB = {
    "散熱與均熱片": {
        "stocks": ["2486"],
        "overview": "隨著 AI 伺服器與高算力需求增加，高效能均熱片成為核心零件。",
        "value_chain": "上游：銅材 -> 中游：一銓(均熱片) -> 下游：伺服器組裝。",
        "competitors": "健策、鴻準、雙鴻。",
        "drivers": "AI 晶片功耗提升、水冷散熱趨勢普及。"
    },
    "LED/MicroLED": {
        "stocks": ["3714", "3595"],
        "overview": "Micro LED 具備高亮度、低功耗特性，為次世代顯示主流。",
        "value_chain": "磊晶(富采) -> 封裝材料(山太士) -> 面板。",
        "competitors": "惠特、錼創、億光。",
        "drivers": "車用顯示器與穿戴裝置需求。"
    },
    "電子玻璃與玻纖布": {
        "stocks": ["1802", "1815"],
        "overview": "玻纖布為高階 PCB (尤其是伺服器板) 的關鍵材料。",
        "value_chain": "玻纖紗 -> 玻纖布(富喬/台玻) -> CCL -> PCB。",
        "competitors": "建榮、台燿、南亞。",
        "drivers": "AI 伺服器帶動高階 CCL 需求。"
    },
    "記憶體產業": {
        "stocks": ["2408"],
        "overview": "DRAM 正處於技術更迭期，HBM 與 DDR5 為未來重心。",
        "value_chain": "製造(南亞科) -> 模組 -> 終端應用。",
        "competitors": "美光、三星、SK海力士。",
        "drivers": "邊緣 AI 手機與筆電更新潮。"
    },
    "高階載板與 PCB": {
        "stocks": ["3037", "4958"],
        "overview": "ABF 載板技術門檻高，是連結晶片與 PCB 的關鍵。",
        "value_chain": "基板材料 -> 載板(欣興/臻鼎) -> 晶片封裝。",
        "competitors": "南電、景碩、Ibiden。",
        "drivers": "先進封裝(CoWoS)需求擴大。"
    },
    "矽光子與光通訊": {
        "stocks": ["3450", "3363", "6451", "3163", "4979", "3081", "2455", "6442"],
        "overview": "解決 AI 運算傳輸頻寬與散熱瓶頸的關鍵技術。",
        "value_chain": "元件(聯亞/全新) -> 模組(光聖/訊芯) -> 交換器。",
        "competitors": "台積電、博通、Intel。",
        "drivers": "800G 交換器需求爆發。"
    }
}

# --- 3. 數據核心 (保留精確技術指標計算) ---
@st.cache_data(ttl=600)
def get_stock_df(sid):
    for suffix in [".TWO", ".TW"]:
        try:
            df = yf.Ticker(f"{sid}{suffix}").history(period="2y", auto_adjust=True)
            if not df.empty and len(df) > 30:
                if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
                # 技術指標
                df['MA5'] = df['Close'].rolling(5).mean()
                df['MA10'] = df['Close'].rolling(10).mean()
                df['MA20'] = df['Close'].rolling(20).mean()
                # MACD (精確計算)
                exp1 = df['Close'].ewm(span=12, adjust=False).mean()
                exp2 = df['Close'].ewm(span=26, adjust=False).mean()
                df['DIF'] = exp1 - exp2
                df['DEA'] = df['DIF'].ewm(span=9, adjust=False).mean()
                df['MACD_Hist'] = df['DIF'] - df['DEA']
                # KD
                low_9, high_9 = df['Low'].rolling(9).min(), df['High'].rolling(9).max()
                rsv = 100 * ((df['Close'] - low_9) / (high_9 - low_9))
                df['K'] = rsv.ewm(com=2, adjust=False).mean()
                df['D'] = df['K'].ewm(com=2, adjust=False).mean()
                # RSI
                delta = df['Close'].diff()
                gain, loss = (delta.where(delta > 0, 0)).rolling(14).mean(), (-delta.where(delta < 0, 0)).rolling(14).mean()
                df['RSI'] = (100 - (100 / (1 + gain/loss)))
                return df
        except: continue
    return pd.DataFrame()

@st.cache_data(ttl=3600)
def get_analysis_data(sid):
    for suffix in [".TWO", ".TW"]:
        try:
            info = yf.Ticker(f"{sid}{suffix}").info
            if info and ('regularMarketPrice' in info or 'symbol' in info):
                return {
                    "EPS": info.get("trailingEps", "N/A"),
                    "營收成長率": info.get('revenueGrowth', 0),
                    "負債比": info.get('debtToEquity', 0),
                    "ROE": f"{round(info.get('returnOnEquity', 0)*100, 2)}%" if info.get('returnOnEquity') else "N/A",
                    "本益比": round(info.get("trailingPE", 0), 2) if info.get("trailingPE") else "N/A",
                    "法人持股": (info.get("heldPercentInstitutions", 0) or 0) * 100
                }
        except: continue
    return None

# --- 4. Sidebar 介面 ---
with st.sidebar:
    st.markdown(f"""<div style="background: linear-gradient(135deg, #1e3a8a, #000000); padding: 15px; border-radius: 12px; border: 1px solid #3b82f6; text-align: center;">
        <h1 style="color: #60a5fa; font-size: 18px; margin: 0;">🚀 戰情操控中心</h1>
        <p style="color: #94a3b8; font-size: 11px; margin-top:5px;">吳秉諺 專屬系統 V16.8</p>
    </div>""", unsafe_allow_html=True)
    
    selected_label = st.selectbox("🎯 選擇標的", list(STOCK_DICT.values()))
    target_sid = selected_label.split(" ")[0]
    view_days = st.slider("📅 顯示天數", 30, 240, 90)
    
    # 補回百科 UI
    st.sidebar.divider()
    current_ind = next((n for n, d in INDUSTRY_DB.items() if target_sid in d.get("stocks", [])), "通用電子")
    st.sidebar.subheader(f"🏢 {current_ind} 百科")
    if current_ind in INDUSTRY_DB:
        d = INDUSTRY_DB[current_ind]
        with st.sidebar.expander("📍 市場規模", expanded=True): st.info(d.get("overview", "暫無"))
        with st.sidebar.expander("🔗 價值鏈分析", expanded=True): st.info(d.get("value_chain", "暫無"))
        with st.sidebar.expander("⚔️ 競爭格局", expanded=False): st.info(d.get("competitors", "暫無"))
        with st.sidebar.expander("📈 驅動因子", expanded=False): st.info(d.get("drivers", "暫無"))

# --- 5. 主圖表介面 ---
df = get_stock_df(target_sid)
a_data = get_analysis_data(target_sid)
col_info, col_main = st.columns([1, 3])

with col_info:
    if not df.empty:
        last, prev = df.iloc[-1], df.iloc[-2]
        diff = round(last['Close'] - prev['Close'], 2)
        m_color = "normal" if diff >= 0 else "inverse" # 紅漲綠跌
        st.metric("最新報價", f"{round(last['Close'], 2)}", f"{diff}", delta_color=m_color)
        st.write(f"**MA5：** :orange[{round(last['MA5'], 2)}]")
        st.write(f"**MA10：** :blue[{round(last['MA10'], 2)}]")
        st.write(f"**MA20：** :violet[{round(last['MA20'], 2)}]")
        
        if a_data:
            st.divider()
            st.write(f"**EPS：** :green[{a_data['EPS']}]")
            st.write(f"**ROE：** :blue[{a_data['ROE']}]")
            st.write(f"**本益比：** `{a_data['本益比']}`")
            st.write(f"**營收成長：** `{round(a_data['營收成長率']*100, 1)}%` {'✅' if a_data['營收成長率']>0 else '🔴'}")
            st.write(f"**負債比：** `{round(a_data['負債比'], 1)}%` {'✅' if a_data['負債比']<60 else '🔴'}")
            st.write(f"**法人持股：** `{round(a_data['法人持股'], 1)}%`")

with col_main:
    if not df.empty:
        plot_df = df.tail(view_days)
        # --- 補回：區間震盪/過熱/安全 資訊面板 ---
        rsi_val = round(plot_df['RSI'].iloc[-1], 2)
        color = "#ef4444" if rsi_val > 80 else ("#10b981" if rsi_val < 40 else "#f59e0b")
        
        st.markdown(f"""<div style="background: linear-gradient(90deg, #111827, #000000); border-left: 10px solid {color}; padding: 20px; border-radius: 12px;">
            <p style="color:white; font-size: 32px; font-weight: 900; margin:0;">{selected_label} <span style="font-size: 24px; color: {color};">RSI: {rsi_val}</span></p>
            <p style="color:{color}; font-size: 22px; font-weight: bold; margin-top: 10px;">{'⚠️【高檔過熱】' if rsi_val > 80 else ('✅【低檔安全】' if rsi_val < 40 else '⚖️【區間震盪】')}</p>
        </div>""", unsafe_allow_html=True)

        # --- 補回： Plotly 四層完整圖表 ---
        fig = make_subplots(rows=4, cols=1, shared_xaxes=True, vertical_spacing=0.04, row_heights=[0.4, 0.1, 0.2, 0.2])
        
        # 1. K線 (紅漲綠跌)
        fig.add_trace(go.Candlestick(x=plot_df.index, open=plot_df['Open'], high=plot_df['High'], low=plot_df['Low'], close=plot_df['Close'],
                                     decreasing=dict(fillcolor='green', line=dict(color='green')),
                                     increasing=dict(fillcolor='red', line=dict(color='red'))), row=1, col=1)
        fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df['MA10'], name="10MA", line=dict(color='#60a5fa')), row=1, col=1)
        
        # 2. 成交量
        fig.add_trace(go.Bar(x=plot_df.index, y=plot_df['Volume'], name="量", marker_color='#334155'), row=2, col=1)
        
        # 3. MACD
        m_colors = ['red' if x > 0 else 'green' for x in plot_df['MACD_Hist']]
        fig.add_trace(go.Bar(x=plot_df.index, y=plot_df['MACD_Hist'], marker_color=m_colors), row=3, col=1)
        fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df['DIF'], name="DIF", line=dict(color='cyan')), row=3, col=1)
        fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df['DEA'], name="DEA", line=dict(color='yellow')), row=3, col=1)
        
        # 4. KD
        fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df['K'], name="K", line=dict(color='white')), row=4, col=1)
        fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df['D'], name="D", line=dict(color='yellow')), row=4, col=1)
        
        fig.update_layout(height=1000, template="plotly_dark", xaxis_rangeslider_visible=False, showlegend=False)
        st.plotly_chart(fig, use_container_width=True)