import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import json
import os

# --- 1. 基本設定 ---
st.set_page_config(layout="wide", page_title="秉諺的黑馬雷達 V8.1")

WATCH_LIST = ["3595", "3037", "2330", "2317", "2454", "3363", "6451", "3163", "4979", "3450", "3081", "2455", "6442"]

# --- 2. 讀取產業百科資料庫 ---
@st.cache_data(ttl=600)
def load_industry_db():
    file_path = "industry_db.json"
    if os.path.exists(file_path):
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

INDUSTRY_DB = load_industry_db()

# --- 3. 核心抓取功能 ---
@st.cache_data(ttl=3600)
def get_stock_info(sid_with_suffix):
    try:
        ticker = yf.Ticker(sid_with_suffix)
        return ticker.info, ticker.news
    except: return {}, []

@st.cache_data(ttl=600)
def get_stock_df(sid):
    for suffix in [".TWO", ".TW"]:
        try:
            full_symbol = f"{sid}{suffix}"
            df = yf.Ticker(full_symbol).history(period="1y", auto_adjust=True)
            if not df.empty:
                if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
                df['MA5'] = df['Close'].rolling(5).mean()
                df['MA10'] = df['Close'].rolling(10).mean()
                df['MA20'] = df['Close'].rolling(20).mean()
                delta = df['Close'].diff()
                gain = (delta.where(delta > 0, 0)).rolling(14).mean()
                loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
                df['RSI'] = (100 - (100 / (1 + gain/loss)))
                return df, full_symbol
        except: continue
    return pd.DataFrame(), None

# --- 4. UI 介面 ---
st.title("📊 秉諺的產業百科黑馬雷達 V8.1")
target_sid = st.sidebar.selectbox("切換監控標的", WATCH_LIST)

df, full_symbol = get_stock_df(target_sid)
info, news_list = get_stock_info(full_symbol) if full_symbol else ({}, [])

# 找出產業對應資料
current_ind_name = "通用電子"
ind_data = {}
for name, data in INDUSTRY_DB.items():
    if target_sid in data.get("stocks", []):
        current_ind_name = name
        ind_data = data
        break

col_info, col_main = st.columns([1, 3])

with col_info:
    if not df.empty:
        st.subheader("🛡️ 技術防線")
        last = df.iloc[-1]
        st.write(f"**5日線：** `{round(last['MA5'], 2)}` {'🔼' if last['Close'] > last['MA5'] else '🔽'}")
        st.write(f"**10日線：** `{round(last['MA10'], 2)}` {'🔼' if last['Close'] > last['MA10'] else '🔽'}")
        st.write(f"**20日線：** `{round(last['MA20'], 2)}` {'🔼' if last['Close'] > last['MA20'] else '🔽'}")

        st.divider()
        st.subheader(f"🏢 {current_ind_name} 百科")
        if ind_data:
            with st.expander("1. 市場規模與成長預測"): st.info(ind_data["overview"])
            with st.expander("2. 價值鏈分析 (上中下游)"): st.info(ind_data["value_chain"])
            with st.expander("3. 競爭格局與市佔率"): st.info(ind_data["competitors"])
            with st.expander("4. 成長驅動因子與挑戰"): st.info(ind_data["drivers"])
        
        if news_list:
            st.divider()
            st.write("**📰 相關新聞：**")
            for item in news_list[:2]:
                st.markdown(f"🔗 [{item['title']}]({item['link']})")

with col_main:
    if not df.empty:
        rsi = df['RSI'].iloc[-1]
        if rsi > 80: status = ("#FF4136", "🔥【極度過熱·分批停利】")
        elif df['MA5'].iloc[-1] > df['MA10'].iloc[-1] > df['MA20'].iloc[-1]: status = ("#2ECC40", "🚀【多頭排列·順勢抱牢】")
        else: status = ("#0074D9", "⚖️【區間震盪·支撐尋找】")
        
        st.markdown(f'''<div style="background-color:{status[0]}; padding:15px; border-radius:10px; color:white; font-weight:bold;">
            <h2 style="margin:0; color:white;">{status[1]} {target_sid}</h2>
            <p style="margin:0; font-size:18px;">最新價: {round(df['Close'].iloc[-1], 2)} | RSI: {round(rsi, 2)}</p></div>''', unsafe_allow_html=True)
        
        fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.7, 0.3], vertical_spacing=0.05)
        fig.add_trace(go.Candlestick(x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'], name="K線"), row=1, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=df['MA5'], name="5日線", line=dict(color='#FF851B')), row=1, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=df['MA20'], name="月線", line=dict(color='#B10DC9', width=2)), row=1, col=1)
        
        v_colors = ['#FF4136' if df['Close'].iloc[i] >= df['Open'].iloc[i] else '#2ECC40' for i in range(len(df))]
        fig.add_trace(go.Bar(x=df.index, y=df['Volume'], name="成交量", marker_color=v_colors), row=2, col=1)
        fig.update_layout(height=700, template="plotly_dark", xaxis_rangeslider_visible=False)
        st.plotly_chart(fig, use_container_width=True)