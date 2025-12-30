import streamlit as st
import yfinance as yf
import plotly.graph_objects as go
import pandas as pd
from datetime import datetime, timedelta

# --- 페이지 설정 (다크 테마는 Streamlit 설정에서 자동 감지되거나 강제 가능) ---
st.set_page_config(
    page_title="Global Financial Dashboard",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- CSS로 다크 테마 강제 및 스타일 조정 (선택 사항) ---
st.markdown("""
    <style>
        .stApp {
            background-color: #0e1117;
            color: #fafafa;
        }
        .metric-card {
            background-color: #262730;
            border: 1px solid #464b5f;
            padding: 15px;
            border-radius: 5px;
            margin-bottom: 10px;
        }
    </style>
""", unsafe_allow_html=True)

# --- 데이터 로드 함수 (캐싱으로 속도 향상) ---
# 실시간성을 위해 ttl(Time To Live)을 짧게 설정 (예: 60초)
@st.cache_data(ttl=60)
def get_market_data(ticker, period="1y", interval="1d"):
    try:
        data = yf.download(ticker, period=period, interval=interval, progress=False)
        return data
    except Exception as e:
        st.error(f"데이터 로드 실패: {ticker} - {e}")
        return pd.DataFrame()

def get_current_price_and_delta(data):
    if data.empty:
        return 0, 0
    
    # 최신 데이터와 그 전일 데이터 가져오기
    # yfinance 최신 버전은 멀티인덱스 컬럼일 수 있으므로 처리
    if isinstance(data.columns, pd.MultiIndex):
        close_data = data['Close'].iloc[:, 0]
    else:
        close_data = data['Close']
        
    current_price = close_data.iloc[-1]
    prev_price = close_data.iloc[-2]
    delta = current_price - prev_price
    
    return current_price, delta

# --- 차트 그리기 함수 (Plotly) ---
def draw_candlestick(data, title):
    if data.empty:
        return go.Figure()

    # 멀티인덱스 처리
    if isinstance(data.columns, pd.MultiIndex):
        df = data.copy()
        df.columns = df.columns.droplevel(1) # Ticker 레벨 제거
    else:
        df = data

    fig = go.Figure(data=[go.Candlestick(
        x=df.index,
        open=df['Open'],
        high=df['High'],
        low=df['Low'],
        close=df['Close'],
        name=title
    )])

    fig.update_layout(
        title=f"{title} Daily Chart",
        template="plotly_dark", # 다크 테마
        xaxis_rangeslider_visible=False,
        height=400,
        margin=dict(l=20, r=20, t=40, b=20)
    )
    return fig

# --- 메인 앱 로직 ---
def main():
    st.title("실시간 금융 시장 대시보드")
    st.caption(f"Last Update: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # 사이드바 설정
    st.sidebar.header("설정")
    refresh = st.sidebar.button("데이터 새로고침")

    # 1. 주요 지수 (Ticker 정의)
    indices = {
        "KOSPI": "^KS11",
        "KOSDAQ": "^KQ11",
        "NASDAQ": "^IXIC",
        "Dollar Index": "DX-Y.NYB"
    }

    # 2. 환율 정보 (Ticker 정의)
    # Yahoo Finance에서 KRW=X는 USD/KRW를 의미
    currencies = {
        "USD/KRW": "KRW=X",
        "JPY/KRW": "JPYKRW=X", # 원/엔 (참고: 야후 심볼 확인 필요, 보통 JPYKRW=X 사용)
        "EUR/KRW": "EURKRW=X"
    }

    # --- 섹션 1: 주요 지수 (상단) ---
    st.subheader("주요 시장 지수")
    col1, col2, col3, col4 = st.columns(4)
    
    cols = [col1, col2, col3, col4]
    
    for i, (name, ticker) in enumerate(indices.items()):
        data = get_market_data(ticker)
        price, delta = get_current_price_and_delta(data)
        
        with cols[i]:
            st.metric(label=name, value=f"{price:,.2f}", delta=f"{delta:,.2f}")

    # --- 섹션 2: 환율 정보 ---
    st.subheader("실시간 환율 (KRW)")
    c_col1, c_col2, c_col3 = st.columns(3)
    c_cols = [c_col1, c_col2, c_col3]

    for i, (name, ticker) in enumerate(currencies.items()):
        data = get_market_data(ticker)
        price, delta = get_current_price_and_delta(data)
        
        with c_cols[i]:
            st.metric(label=name, value=f"{price:,.2f} 원", delta=f"{delta:,.2f} 원", delta_color="inverse")

    # --- 섹션 3: 상세 차트 ---
    st.divider()
    st.subheader("상세 차트 분석 (일봉)")
    
    # 탭으로 구분하여 차트 표시
    all_tickers = {**indices, **currencies}
    tabs = st.tabs(list(all_tickers.keys()))

    for i, (name, ticker) in enumerate(all_tickers.items()):
        with tabs[i]:
            data = get_market_data(ticker)
            fig = draw_candlestick(data, name)
            st.plotly_chart(fig, use_container_width=True)

if __name__ == "__main__":
    main()