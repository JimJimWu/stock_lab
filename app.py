import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import datetime

# --- 1. 基本設定 ---
st.set_page_config(layout="wide", page_title="秉諺的黑馬雷達 V7.8")

WATCH_LIST = ["3595", "3037", "2330", "2317", "2454", "3363", "6451", "3163", "4979", "3450", "3081", "2455", "6442"]

# --- 2. 核心抓取函式 (加入快取保護，減少被封鎖機率) ---
@st.cache_data(ttl=3600)  # 基本資料與新聞快取 1 小時
def get_stock_info(sid_with_suffix):
    try:
        ticker = yf.Ticker(sid_with_suffix)
        # 這裡分開抓，避免一個失敗全部掛掉
        info = ticker.info
        news = ticker.news
        return info, news
    except:
        return {}, []

@st.cache_data(ttl=600)   # 股價 K 線快取 10 分鐘
def get_stock_df(sid):
    for suffix in [".TWO", ".TW"]:
        try:
            full_symbol = f"{sid}{suffix}"
            ticker = yf.Ticker(full_symbol)
            df = ticker.history(period="1y", auto_adjust=True)
            if not df.empty:
                if isinstance(df.columns, pd.MultiIndex):
                    df.columns = df.columns.get_level_values(0)
                # 均線計算
                df['MA5'] = df['Close'].rolling(5).mean()
                df['MA10'] = df['Close'].rolling(10).mean()
                df['MA20'] = df['Close'].rolling(20).mean()
                df['VOL_MA5'] = df['Volume'].rolling(5).mean()
                # RSI
                delta = df['Close'].diff()
                gain = (delta.where(delta > 0, 0)).rolling(14).mean()
                loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
                df['RSI'] = (100 - (100 / (1 + gain/loss)))
                return df, full_symbol
        except:
            continue
    return pd.DataFrame(), None

# --- 3. UI 介面 ---
st.title("📊 秉諺的黑馬雷達 V7.8")
target_sid = st.sidebar.selectbox("切換監控標的", WATCH_LIST)

# 執行抓取
df, full_symbol = get_stock_df(target_sid)

if full_symbol:
    # 這裡使用帶快取的函式
    info, news_list = get_stock_info(full_symbol)
else:
    info, news_list = {}, []

col_info, col_main = st.columns([1, 3])

# --- A. 左側資訊欄 ---
with col_info:
    if not df.empty:
        last = df.iloc[-1]
        st.subheader("💎 均線狀態")
        st.write(f"5日線 (短)：{round(last['MA5'], 2)}")
        st.write(f"10日線 (中)：{round(last['MA10'], 2)}")
        st.write(f"20日線 (月)：{round(last['MA20'], 2)}")
        
        if last['MA5'] > last['MA10'] > last['MA20']:
            st.success("🔥 狀態：強勢多頭排列")
        elif last['Close'] < last['MA20']:
            st.warning("❄️ 狀態：跌破月線轉弱")
            
        st.divider()
        st.subheader("💡 深度見解")
        pe_ratio = info.get('trailingPE', 'N/A')
        st.write(f"**目前本益比 (PE)：** {round(pe_ratio, 2) if pe_ratio != 'N/A' else 'N/A'}")
        
        if news_list:
            st.write("**📰 最新相關新聞：**")
            for item in news_list[:3]:
                st.markdown(f"🔗 [{item['title']}]({item['link']})")
        else:
            st.write("暫無即時新聞或 Yahoo 限制存取。")

# --- B. 右側圖表欄 ---
with col_main:
    if not df.empty:
        rsi = df['RSI'].iloc[-1]
        if rsi > 85: bg, msg = "#FF4136", "⚠️【極度過熱】"
        elif rsi > 70: bg, msg = "#FFDC00", "🟡【高檔震盪】"
        else: bg, msg = "#2ECC40", "✅【趨勢安全】"
        
        st.markdown(f'<div style="background-color:{bg}; padding:15px; border-radius:10px; color:black; font-weight:bold;">'
                    f'<h2 style="margin:0;">{msg} {target_sid}</h2>'
                    f'<p style="margin:0; font-size:18px;">最新價: {round(df["Close"].iloc[-1], 2)} | RSI: {round(rsi, 2)}</p></div>', unsafe_allow_html=True)
        
        fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.7, 0.3], vertical_spacing=0.05)
        fig.add_trace(go.Candlestick(x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'], name="K線",
            increasing_line_color='#FF4136', increasing_fillcolor='#FF4136',
            decreasing_line_color='#2ECC40', decreasing_fillcolor='#2ECC40'), row=1, col=1)
        
        fig.add_trace(go.Scatter(x=df.index, y=df['MA5'], name="5日線", line=dict(color='#FF851B', width=1.5)), row=1, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=df['MA10'], name="10日線", line=dict(color='#0074D9', width=1.5)), row=1, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=df['MA20'], name="月線", line=dict(color='#B10DC9', width=2)), row=1, col=1)
        
        v_colors = ['#FF4136' if df['Close'].iloc[i] >= df['Open'].iloc[i] else '#2ECC40' for i in range(len(df))]
        fig.add_trace(go.Bar(x=df.index, y=df['Volume'], name="成交量", marker_color=v_colors, opacity=0.8), row=2, col=1)
        
        fig.update_layout(height=750, template="plotly_dark", xaxis_rangeslider_visible=False)
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.error("暫時無法抓取該標的資料。")