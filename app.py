import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import datetime

# --- 1. 基本設定 ---
st.set_page_config(layout="wide", page_title="秉諺的黑馬雷達 V8.0")

WATCH_LIST = ["3595", "3037", "2330", "2317", "2454", "3363", "6451", "3163", "4979", "3450", "3081", "2455", "6442"]

# --- 2. 產業百科全書資料庫 (含 4 大維度分析) ---
INDUSTRY_DB = {
    "半導體代工/IC設計": {
        "stocks": ["2330", "2454"],
        "overview": "📍 **市場規模**：2026 年全球半導體產值預估突破 7,000 億美元。AI 晶片年成長率 > 30%。",
        "value_chain": "🔗 **價值鏈**：IP設計(Arm/聯發科) -> 晶圓代工(台積電) -> 封裝測試(日月光)。",
        "competitors": "⚔️ **競爭格局**：台積電(市佔 60%↑, 先進製程 90%↑)、三星、Intel。",
        "drivers": "📈 **驅動因子**：邊緣 AI 運算需求、2奈米製程量產、HPC 高效能運算。"
    },
    "載板/PCB/散熱": {
        "stocks": ["3037", "3163", "3363", "3595"],
        "overview": "📍 **市場規模**：ABF 載板 2026 年供需缺口預計再次擴大，產值年增 10-15%。",
        "value_chain": "🔗 **價值鏈**：上游(CCL/銅箔) -> 中游(ABF載板/散熱模組) -> 下游(伺服器組裝)。",
        "competitors": "⚔️ **競爭格局**：欣興、Ibiden、南電；散熱則為雙鴻、尼得科超眾。",
        "drivers": "📈 **驅動因子**：AI 伺服器功耗飆升至 1000W↑，帶動液冷與高層數板需求。"
    },
    "矽光子/光通訊": {
        "stocks": ["6442", "3081", "3450", "4979", "6451", "2455", "6442"],
        "overview": "📍 **市場規模**：2030 年產值上看 78 億美元，CPO 封裝滲透率將大幅提升。",
        "value_chain": "🔗 **價值鏈**：上游(磊晶/元件) -> 中游(光模組/CPO封裝) -> 下游(大型資料中心)。",
        "competitors": "⚔️ **競爭格局**：聯亞(磊晶)、光聖(傳輸)、博通(交換器)、Intel。",
        "drivers": "📈 **驅動因子**：800G/1.6T 高速傳輸需求、解決 AI 算力中心能源損耗瓶頸。"
    }
}

# --- 3. 核心功能 (Cache 保護) ---
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
st.title("📊 秉諺的產業百科黑馬雷達 V8.0")
target_sid = st.sidebar.selectbox("切換監控標的", WATCH_LIST)

df, full_symbol = get_stock_df(target_sid)
info, news_list = get_stock_info(full_symbol) if full_symbol else ({}, [])

# 找出產業對應資料
current_ind_name = "通用電子"
ind_data = {}
for name, data in INDUSTRY_DB.items():
    if target_sid in data["stocks"]:
        current_ind_name = name
        ind_data = data
        break

col_info, col_main = st.columns([1, 3])

# --- A. 左側資訊欄 ---
with col_info:
    if not df.empty:
        # 1. 均線診斷
        st.subheader("🛡️ 技術防線")
        last = df.iloc[-1]
        st.write(f"**5日線：** `{round(last['MA5'], 2)}` {'🔼' if last['Close'] > last['MA5'] else '🔽'}")
        st.write(f"**10日線：** `{round(last['MA10'], 2)}` {'🔼' if last['Close'] > last['MA10'] else '🔽'}")
        st.write(f"**20日線：** `{round(last['MA20'], 2)}` {'🔼' if last['Close'] > last['MA20'] else '🔽'}")

        # 2. 產業百科全書 (折疊選單)
        st.divider()
        st.subheader(f"🏢 {current_ind_name} 百科")
        if ind_data:
            with st.expander("1. 市場規模與成長預測", expanded=False):
                st.info(ind_data["overview"])
            with st.expander("2. 價值鏈分析 (上中下游)", expanded=False):
                st.info(ind_data["value_chain"])
            with st.expander("3. 競爭格局與市佔率", expanded=False):
                st.info(ind_data["competitors"])
            with st.expander("4. 成長驅動因子與挑戰", expanded=False):
                st.info(ind_data["drivers"])
        
        # 3. 即時新聞
        if news_list:
            st.divider()
            st.write("**📰 相關新聞：**")
            for item in news_list[:2]:
                st.markdown(f"🔗 [{item['title']}]({item['link']})")
        else:
            st.caption("ℹ️ Yahoo 新聞暫時受限，請參考產業百科。")

# --- B. 右側圖表欄 ---
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