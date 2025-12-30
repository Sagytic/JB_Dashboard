import streamlit as st
import yfinance as yf
import plotly.graph_objects as go
import pandas as pd
from datetime import datetime
import time

# --- 페이지 설정 ---
st.set_page_config(
    page_title="Financial Dashboard",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# --- CSS 스타일링 ---
st.markdown("""
    <style>
        .stApp {
            background-color: #0e1117;
            color: #fafafa;
        }
        [data-testid="stMetricLabel"] {
            font-size: 14px;
            color: #b0b0b0;
        }
        [data-testid="stMetricValue"] {
            font-size: 20px;
            font-weight: bold;
        }
        /* 캡션(기준 텍스트) 스타일 */
        [data-testid="stCaptionContainer"] {
            font-size: 12px;
            color: #666;
            margin-top: -10px;
            margin-bottom: 10px;
        }
        /* 차트 모드바 스타일링 */
        .modebar-btn {
            color: #b0b0b0 !important;
        }
        /* 버튼 스타일 조정 */
        div.stButton > button {
            padding: 0.2rem 0.5rem;
            font-size: 0.8rem;
        }
    </style>
""", unsafe_allow_html=True)

# --- [성능 개선] 데이터 일괄 로드 함수 ---
@st.cache_data(ttl=60)
def get_batch_data(tickers):
    try:
        # 여러 종목을 한 번에 다운로드 (group_by='ticker'로 종목별로 묶음)
        # 이렇게 하면 네트워크 요청을 1번만 보내므로 속도가 훨씬 빠릅니다.
        data = yf.download(tickers, period="1y", interval="1d", group_by='ticker', progress=False)
        return data
    except Exception:
        return pd.DataFrame()

# --- 데이터 전처리 함수 (단일 종목 처리) ---
def process_ticker_data(df, is_jpy=False):
    # df는 이미 특정 종목의 데이터프레임 (Open, High, Low, Close 컬럼 보유)
    if df.empty:
        return 0, 0, pd.DataFrame(), False
    
    # 원본 보호를 위해 복사
    df = df.copy()

    # [수정] NaN 처리 강화: Close(종가)가 없는 행(휴장일 등)은 과감히 제거
    # yfinance 배차 다운로드는 모든 종목의 인덱스를 합치기 때문에 
    # 특정 종목이 거래되지 않은 날은 NaN으로 들어옵니다. 이를 제거해야 합니다.
    df = df.dropna(subset=['Close'])

    if df.empty:
        return 0, 0, pd.DataFrame(), False

    # 데이터 누락 방지 (NaN 채우기)
    cols_to_check = ['Open', 'High', 'Low']
    for col in cols_to_check:
        if col in df.columns:
            df[col] = df[col].fillna(df['Close'])

    if is_jpy:
        df = df * 100

    current_price = df['Close'].iloc[-1]
    
    if len(df) >= 2:
        prev_price = df['Close'].iloc[-2]
        delta = current_price - prev_price
    else:
        delta = 0
    
    # [추가] 최종 값에도 NaN이 남아있을 경우 0으로 처리 (에러 방지)
    if pd.isna(current_price): current_price = 0.0
    if pd.isna(delta): delta = 0.0

    # 데이터가 "납작한지" 확인 (선 차트 전환용)
    is_flat = (df['High'] == df['Low']).mean() > 0.5
        
    return current_price, delta, df, is_flat

# --- 차트 그리기 함수 ---
def draw_mini_chart(df, ticker_id, is_flat=False, color_up="#2ecc71", color_down="#ff4b4b"):
    if df.empty:
        return go.Figure()

    if is_flat:
        fig = go.Figure(data=[go.Scatter(
            x=df.index,
            y=df['Close'],
            mode='lines',
            line=dict(color='#3498db', width=2),
            name='Close'
        )])
    else:
        fig = go.Figure(data=[go.Candlestick(
            x=df.index,
            open=df['Open'],
            high=df['High'],
            low=df['Low'],
            close=df['Close'],
            increasing_line_color=color_up,
            decreasing_line_color=color_down,
            showlegend=False
        )])

    fig.update_layout(
        template="plotly_dark",
        margin=dict(l=0, r=0, t=10, b=0),
        height=250,
        xaxis_rangeslider_visible=False,
        xaxis=dict(showgrid=False, showticklabels=True),
        yaxis=dict(showgrid=True, showticklabels=True, side="right"),
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        dragmode='zoom',
        uirevision=ticker_id 
    )
    return fig

# --- 카드 생성 함수 (Batch Data 사용) ---
def create_card(title, sub_label, ticker, batch_data, is_jpy=False, fmt="{:,.2f}", reference_text="기준: 전일 종가"):
    with st.container(border=True):
        # 전체 데이터셋에서 내 티커에 해당하는 데이터만 쏙 뽑아냄
        ticker_df = pd.DataFrame()
        try:
            if not batch_data.empty:
                # yfinance 멀티인덱스 구조 처리
                if isinstance(batch_data.columns, pd.MultiIndex):
                    try:
                        ticker_df = batch_data[ticker]
                    except KeyError:
                        pass # 데이터에 해당 티커가 없음
                else:
                    # 티커가 1개뿐이거나 구조가 다를 경우 통째로 사용
                    ticker_df = batch_data
        except Exception:
            pass

        price, delta, df, is_flat = process_ticker_data(ticker_df, is_jpy)
        
        st.metric(
            label=f"{title} ({sub_label})", 
            value=fmt.format(price), 
            delta=fmt.format(delta),
            delta_color="normal" 
        )
        # [요청사항] 기준 시점 표시 (파라미터로 변경 가능)
        st.caption(reference_text)
        
        if not df.empty:
            fig = draw_mini_chart(df, ticker_id=ticker, is_flat=is_flat)
            st.plotly_chart(
                fig, 
                use_container_width=True, 
                config={
                    'displayModeBar': True,
                    'displaylogo': False,
                    'modeBarButtonsToRemove': ['select2d', 'lasso2d'],
                }
            )
        else:
            st.warning("데이터 로드 실패")

# --- 메인 앱 로직 ---
def main():
    # 1. 상단 레이아웃
    col_title, col_empty, col_toggle, col_btn = st.columns([5, 1, 3, 2])
    
    with col_title:
        st.title("Global Financial Dashboard")
        
    with col_toggle:
        st.write("") 
        # [요청사항] 텍스트 변경
        auto_refresh = st.toggle("10초 단위 자동 새로고침", value=False)
        
    with col_btn:
        st.write("") 
        # [요청사항] 버튼 텍스트 추가
        if st.button("🔄 즉시 새로고침", use_container_width=True):
            st.cache_data.clear()
            st.rerun()

    status_placeholder = st.empty()

    # --- 데이터 정의 및 일괄 로드 (Batch Download) ---
    indices = {
        "KOSPI": "^KS11", "KOSDAQ": "^KQ11", 
        "NASDAQ": "^IXIC", "Dollar Index": "DX-Y.NYB"
    }
    currencies = {
        "USD/KRW": "KRW=X", "JPY/KRW": "JPYKRW=X",
        "EUR/KRW": "EURKRW=X", "CNY/KRW": "CNYKRW=X"
    }
    cryptos = {
        "Bitcoin": "BTC-KRW", "Ethereum": "ETH-KRW"
    }
    
    # 모든 티커를 리스트로 합침
    all_tickers = list(indices.values()) + list(currencies.values()) + list(cryptos.values())
    
    # [성능 핵심] 여기서 한 번에 다 받아옴
    with st.spinner('데이터를 불러오는 중...'):
        batch_data = get_batch_data(all_tickers)

    # 2. Market Indices
    st.subheader("Market Indices")
    idx_col1, idx_col2, idx_col3, idx_col4 = st.columns(4)
    with idx_col1: create_card("KOSPI", "Index", indices["KOSPI"], batch_data)
    with idx_col2: create_card("KOSDAQ", "Index", indices["KOSDAQ"], batch_data)
    with idx_col3: create_card("NASDAQ", "Index", indices["NASDAQ"], batch_data)
    with idx_col4: create_card("Dollar Index", "Index", indices["Dollar Index"], batch_data)

    # 3. Currencies
    st.divider()
    st.subheader("Exchange Rates (KRW)")
    curr_col1, curr_col2, curr_col3, curr_col4 = st.columns(4)
    with curr_col1: create_card("USD/KRW", "1 USD", currencies["USD/KRW"], batch_data)
    with curr_col2: create_card("JPY/KRW", "100 JPY", currencies["JPY/KRW"], batch_data, is_jpy=True)
    with curr_col3: create_card("EUR/KRW", "1 EUR", currencies["EUR/KRW"], batch_data)
    with curr_col4: create_card("CNY/KRW", "1 CNY", currencies["CNY/KRW"], batch_data)

    # 4. Crypto
    st.divider()
    st.subheader("Crypto Assets (KRW)")
    cry_col1, cry_col2 = st.columns(2)
    # [수정] 코인용 기준 텍스트 전달
    with cry_col1: create_card("Bitcoin", "BTC/KRW", cryptos["Bitcoin"], batch_data, fmt="{:,.0f}", reference_text="기준: 전일 종가 (UTC 0시)")
    with cry_col2: create_card("Ethereum", "ETH/KRW", cryptos["Ethereum"], batch_data, fmt="{:,.0f}", reference_text="기준: 전일 종가 (UTC 0시)")

    # --- 자동 새로고침 로직 ---
    if auto_refresh:
        for i in range(10, 0, -1):
            status_placeholder.caption(f"⏳ {i}초 후 업데이트...")
            time.sleep(1)
        st.cache_data.clear()
        st.rerun()
    else:
        status_placeholder.empty()

if __name__ == "__main__":
    main()