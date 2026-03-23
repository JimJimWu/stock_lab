import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import datetime

# --- 1. 頁面基本設定 ---
st.set_page_config(layout="wide", page_title="秉諺的黑馬雷達 V7.8")

# --- 2. 核心監控名單 (同步 auto_scan.py) ---
WATCH_LIST = [
    "3595", "3037", "2330", "2317", "2454", 
    "3363", "6451", "3163", "4979", "3450", 
    "3081", "2455", "6442"
]

# --- 3. 數據與指標計算 ---
@st.cache_data(ttl=600)
def get_processed_data(sid):
    for suffix in [".TWO", ".TW"]:
        try:
            df = yf.download(f"{sid}{suffix}", period="1y", progress=False)
            if not df.empty:
                if isinstance(df.columns, pd.MultiIndex):
                    df.columns = df.columns.get_level_values(0)
                
                # 計算 RSI (14)
                delta = df['Close'].diff()
                gain = (delta.where(delta > 0, 0)).rolling(14).mean()
                loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
                df['RSI'] = (100 - (100 / (1 + gain/loss))).round(2)
                
                # 計算 MACD
                exp1 = df['Close'].ewm(span=12, adjust=False).mean()
                exp2 = df['Close'].ewm(span=26, adjust=False).mean()
                df['DIF'] = exp1 - exp2
                df['MACD_Sig'] = df['DIF'].ewm(span=9, adjust=False).mean()
                df['MACD_Hist'] = df['DIF'] - df['MACD_Sig']
                
                # 均線與量能
                df['MA5'] = df['Close'].rolling(5).mean()
                df['VOL_MA5'] = df['Volume'].rolling(5).mean()
                return df
        except:
            continue
    return pd.DataFrame()

# --- 4. UI 介面 ---
st.title("📊 秉諺的黑馬雷達 V7.8")

# 側邊欄控制
st.sidebar.title("⚙️ 策略中心")
manual_sid = st.sidebar.text_input("🔍 手動輸入代號", value="3595")
if st.sidebar.button("🚀 執行全名單掃描"):
    results = []
    for s in WATCH_LIST:
        d = get_processed_data(s)
        if not d.empty:
            curr = d.iloc[-1]
            ratio = curr['Volume'] / curr['VOL_MA5'] if curr['VOL_MA5'] > 0 else 0
            sig = "🔥 金叉" if d.iloc[-2]['MACD_Hist'] <= 0 and curr['MACD_Hist'] > 0 else ("📈 多頭" if curr['MACD_Hist'] > 0 else "📉 整理")
            results.append({"股票": s, "訊號": sig, "RSI": curr['RSI'], "量能倍數": round(ratio, 2)})
    st.session_state['scan_results'] = pd.DataFrame(results)

# --- 主畫面佈局 ---
target_sid = manual_sid
col_list, col_main = st.columns([1, 3])

with col_list:
    if 'scan_results' in st.session_state:
        st.subheader("📍 即時監控")
        target_sid = st.selectbox("切換標的", st.session_state['scan_results']['股票'])
        st.dataframe(st.session_state['scan_results'], hide_index=True)

with col_main:
    df = get_processed_data(target_sid)
    if not df.empty:
        last = df.iloc[-1]
        rsi = last['RSI']
        vol_ratio = last['Volume'] / last['VOL_MA5'] if last['VOL_MA5'] > 0 else 0
        
        # --- 三色預警邏輯 ---
        if rsi > 85:
            color, msg = "#FF4136", "⚠️【極度過熱·禁止追高】"
        elif rsi > 70:
            color, msg = "#FFDC00", "🟡【高檔震盪·注意回檔】"
        else:
            color, msg = "#2ECC40", "✅【趨勢安全·量能發動】"
        
        # 頂部狀態顯示
        st.markdown(f"""
        <div style="background-color:{color}; padding:15px; border-radius:10px; color:black; font-weight:bold;">
            <h2 style="margin:0;">{msg} {target_sid}</h2>
            <p style="margin:5px 0 0 0; font-size:18px;">
                RSI: {rsi} | 5日線支撐: {round(last['MA5'], 2)} | 量能倍數: {round(vol_ratio, 2)}x
            </p>
        </div>
        """, unsafe_allow_html=True)
        
        # 繪圖
        fig = make_subplots(rows=4, cols=1, shared_xaxes=True, row_heights=[0.5, 0.15, 0.15, 0.2], vertical_spacing=0.03)
        fig.add_trace(go.Candlestick(x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'], name="K線"), row=1, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=df['MA5'], name="5日線", line=dict(color='#FF851B', width=2)), row=1, col=1)
        fig.add_trace(go.Bar(x=df.index, y=df['Volume'], name="成交量", marker_color='#AAAAAA'), row=2, col=1)
        fig.add_trace(go.Bar(x=df.index, y=df['MACD_Hist'], name="MACD", marker_color=['#FF4136' if h>=0 else '#3D9970' for h in df['MACD_Hist']]), row=3, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=df['RSI'], name="RSI", line=dict(color='#87CEEB')), row=4, col=1)
        fig.update_layout(height=850, template="plotly_dark", xaxis_rangeslider_visible=False, showlegend=False)
        st.plotly_chart(fig, use_container_width=True)