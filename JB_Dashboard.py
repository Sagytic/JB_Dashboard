import streamlit as st
import yfinance as yf
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd
import numpy as np 
from datetime import datetime, timedelta
import time

# --- 페이지 설정 ---
st.set_page_config(
    page_title="JB Dashboard",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# --- CSS 스타일링 (스텔스 모드 적용: Streamlit 티 안 나게 하기) ---
st.markdown("""
    <style>
        /* 1. 전체 배경 및 폰트 설정 */
        .stApp {
            background-color: #0e1117;
            color: #fafafa;
        }
        
        /* 2. Streamlit 기본 UI 요소 숨기기 (스텔스 모드) */
        #MainMenu {visibility: hidden;} /* 우측 상단 햄버거 메뉴 숨김 */
        header {visibility: hidden;}    /* 상단 헤더 숨김 */
        footer {visibility: hidden;}    /* 하단 'Made with Streamlit' 숨김 */
        .stDeployButton {display:none;} /* 배포 버튼 숨김 */
        [data-testid="stToolbar"] {visibility: hidden;} /* 우측 상단 툴바 숨김 */
        [data-testid="stDecoration"] {display:none;} /* 상단 데코레이션 바 숨김 */

        /* 3. 콘텐츠 영역 상단 여백 제거 (헤더가 사라진 자리 메우기) */
        .block-container {
            padding-top: 1rem !important; 
            padding-bottom: 0rem !important;
        }

        /* 4. 커스텀 스타일링 */
        [data-testid="stMetricLabel"] {
            font-size: 14px;
            color: #b0b0b0;
        }
        [data-testid="stMetricValue"] {
            font-size: 20px;
            font-weight: bold;
        }
        [data-testid="stCaptionContainer"] {
            font-size: 12px;
            color: #666;
            margin-top: -10px;
            margin-bottom: 10px;
        }
        .modebar-btn {
            color: #b0b0b0 !important;
        }
        div.stButton > button {
            padding: 0.2rem 0.5rem;
            font-size: 0.8rem;
        }
        /* Quant Lab 스타일 */
        .quant-header {
            font-size: 1.5rem;
            font-weight: bold;
            color: #fafafa;
            margin-top: 2rem;
            margin-bottom: 1rem;
            border-bottom: 1px solid #444;
        }
    </style>
""", unsafe_allow_html=True)

# --- [성능 개선] 데이터 일괄 로드 함수 ---
@st.cache_data(ttl=60)
def get_batch_data(tickers):
    try:
        data = yf.download(tickers, period="1y", interval="1d", group_by='ticker', progress=False)
        return data
    except Exception:
        return pd.DataFrame()

# --- [Technical] 기술적 지표 계산 함수 ---
def add_technical_indicators(df):
    if df.empty or len(df) < 20:
        return df
    
    # 1. 이동평균선 (SMA 20)
    df['SMA_20'] = df['Close'].rolling(window=20).mean()
    
    # 2. 볼린저 밴드 (Bollinger Bands)
    df['STD_20'] = df['Close'].rolling(window=20).std()
    df['Upper_Band'] = df['SMA_20'] + (df['STD_20'] * 2)
    df['Lower_Band'] = df['SMA_20'] - (df['STD_20'] * 2)
    
    # 3. RSI (Relative Strength Index)
    delta = df['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    df['RSI'] = 100 - (100 / (1 + rs))
    
    return df

# --- [Quant] 몬테카를로 시뮬레이션 함수 ---
def run_monte_carlo(df, simulations=50, days=30):
    if df.empty:
        return None
    
    log_returns = np.log(1 + df['Close'].pct_change())
    
    u = log_returns.mean()
    var = log_returns.var()
    drift = u - (0.5 * var)
    stdev = log_returns.std()
    
    last_price = df['Close'].iloc[-1]
    prediction_dates = [df.index[-1] + timedelta(days=x) for x in range(1, days+1)]
    
    simulation_df = pd.DataFrame()
    simulation_df['Date'] = prediction_dates
    simulation_df.set_index('Date', inplace=True)
    
    for i in range(simulations):
        Z = np.random.normal(0, 1, days)
        daily_returns = np.exp(drift + stdev * Z)
        
        price_paths = [last_price]
        for r in daily_returns:
            price_paths.append(price_paths[-1] * r)
        
        simulation_df[f'Sim_{i}'] = price_paths[1:]
        
    return simulation_df

# --- 데이터 전처리 함수 ---
def process_ticker_data(df, is_jpy=False):
    if df.empty:
        return 0, 0, pd.DataFrame(), False
    
    df = df.copy()
    df = df.dropna(subset=['Close'])

    if df.empty:
        return 0, 0, pd.DataFrame(), False

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
    
    if pd.isna(current_price): current_price = 0.0
    if pd.isna(delta): delta = 0.0

    is_flat = (df['High'] == df['Low']).mean() > 0.5
        
    return current_price, delta, df, is_flat

# --- 차트 그리기 함수 (Advanced) ---
def draw_chart(df, ticker_id, is_flat=False, show_tech=False):
    if df.empty:
        return go.Figure()

    fig = go.Figure()

    # 1. 기본 캔들/라인 차트
    if is_flat:
        fig.add_trace(go.Scatter(x=df.index, y=df['Close'], mode='lines', 
                                 line=dict(color='#3498db', width=2), name='Close'))
    else:
        fig.add_trace(go.Candlestick(
            x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'],
            increasing_line_color="#2ecc71", decreasing_line_color="#ff4b4b", name='Price'
        ))

    # 2. [Technical] 기술적 지표 추가
    if show_tech and 'SMA_20' in df.columns:
        fig.add_trace(go.Scatter(
            x=df.index, y=df['Upper_Band'], line=dict(color='rgba(255, 255, 255, 0)'),
            showlegend=False, hoverinfo='skip'
        ))
        fig.add_trace(go.Scatter(
            x=df.index, y=df['Lower_Band'], fill='tonexty', 
            fillcolor='rgba(108, 92, 231, 0.1)', line=dict(color='rgba(255, 255, 255, 0)'),
            name='Bollinger Band', hoverinfo='skip'
        ))
        fig.add_trace(go.Scatter(
            x=df.index, y=df['SMA_20'], line=dict(color='#f1c40f', width=1), name='SMA 20'
        ))

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
        uirevision=ticker_id,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
    )
    return fig

# --- 카드 생성 함수 ---
def create_card(title, sub_label, ticker, batch_data, is_jpy=False, fmt="{:,.2f}", 
                reference_text="기준: 전일 종가", show_chart=True, show_tech=False):
    with st.container(border=True):
        ticker_df = pd.DataFrame()
        try:
            if not batch_data.empty:
                if isinstance(batch_data.columns, pd.MultiIndex):
                    try:
                        ticker_df = batch_data[ticker]
                    except KeyError:
                        pass
                else:
                    ticker_df = batch_data
        except Exception:
            pass

        price, delta, df, is_flat = process_ticker_data(ticker_df, is_jpy)
        
        if show_tech and not df.empty:
            df = add_technical_indicators(df)

        st.metric(
            label=f"{title} ({sub_label})", 
            value=fmt.format(price), 
            delta=fmt.format(delta),
            delta_color="normal" 
        )
        st.caption(reference_text)
        
        if show_chart:
            if not df.empty:
                fig = draw_chart(df, ticker_id=ticker, is_flat=is_flat, show_tech=show_tech)
                st.plotly_chart(fig, use_container_width=True, 
                                config={'displayModeBar': True, 'displaylogo': False, 
                                        'modeBarButtonsToRemove': ['select2d', 'lasso2d']})
            else:
                st.warning("데이터 로드 실패")

# --- 메인 앱 로직 ---
def main():
    col_title, col_simple, col_toggle, col_btn = st.columns([4, 2, 3, 1])
    
    with col_title:
        st.title("Global Financial Dashboard")
    
    with col_simple:
        st.write("")
        simple_mode = st.toggle("간편 모드 (차트 숨기기)", value=False)
        
    with col_toggle:
        st.write("") 
        auto_refresh = st.toggle("10초 단위 자동 새로고침", value=False)
        
    with col_btn:
        st.write("") 
        if st.button("즉시 새로고침", use_container_width=True):
            st.cache_data.clear()
            st.rerun()

    status_placeholder = st.empty()

    # --- 데이터 정의 ---
    indices = {"KOSPI": "^KS11", "KOSDAQ": "^KQ11", "NASDAQ": "^IXIC", "Dollar Index": "DX-Y.NYB"}
    currencies = {"USD/KRW": "KRW=X", "JPY/KRW": "JPYKRW=X", "EUR/KRW": "EURKRW=X", "CNY/KRW": "CNYKRW=X"}
    cryptos = {"Bitcoin": "BTC-KRW", "Ethereum": "ETH-KRW"}
    
    all_tickers = list(indices.values()) + list(currencies.values()) + list(cryptos.values())
    
    with st.spinner('데이터 분석 및 로딩 중...'):
        batch_data = get_batch_data(all_tickers)

    show_charts = not simple_mode

    # [Quant 옵션] 사이드바 설정 - 모든 옵션 True
    st.sidebar.header("Quant Lab Settings")
    show_tech = st.sidebar.checkbox("기술적 지표 (Bollinger/SMA)", value=True, help="차트에 볼린저 밴드와 이동평균선을 오버레이합니다.")
    show_heatmap = st.sidebar.checkbox("자산 상관관계 (Heatmap)", value=True, help="자산 간의 가격 움직임 상관계수를 분석합니다.")
    show_monte = st.sidebar.checkbox("몬테카를로 시뮬레이션", value=True, help="향후 30일간의 가격 변동 확률을 시뮬레이션합니다.")

    # 1, 2, 3 섹션 (기존 카드 뷰)
    st.subheader("Market Indices")
    idx_col1, idx_col2, idx_col3, idx_col4 = st.columns(4)
    with idx_col1: create_card("KOSPI", "Index", indices["KOSPI"], batch_data, show_chart=show_charts, show_tech=show_tech)
    with idx_col2: create_card("KOSDAQ", "Index", indices["KOSDAQ"], batch_data, show_chart=show_charts, show_tech=show_tech)
    with idx_col3: create_card("NASDAQ", "Index", indices["NASDAQ"], batch_data, show_chart=show_charts, show_tech=show_tech)
    with idx_col4: create_card("Dollar Index", "Index", indices["Dollar Index"], batch_data, show_chart=show_charts, show_tech=show_tech)

    st.divider()
    st.subheader("Exchange Rates (KRW)")
    curr_col1, curr_col2, curr_col3, curr_col4 = st.columns(4)
    with curr_col1: create_card("USD/KRW", "1 USD", currencies["USD/KRW"], batch_data, show_chart=show_charts, show_tech=show_tech)
    with curr_col2: create_card("JPY/KRW", "100 JPY", currencies["JPY/KRW"], batch_data, is_jpy=True, show_chart=show_charts, show_tech=show_tech)
    with curr_col3: create_card("EUR/KRW", "1 EUR", currencies["EUR/KRW"], batch_data, show_chart=show_charts, show_tech=show_tech)
    with curr_col4: create_card("CNY/KRW", "1 CNY", currencies["CNY/KRW"], batch_data, show_chart=show_charts, show_tech=show_tech)

    st.divider()
    st.subheader("Crypto Assets (KRW)")
    cry_col1, cry_col2 = st.columns(2)
    with cry_col1: create_card("Bitcoin", "BTC/KRW", cryptos["Bitcoin"], batch_data, fmt="{:,.0f}", reference_text="기준: 전일 종가 (UTC 0시)", show_chart=show_charts, show_tech=show_tech)
    with cry_col2: create_card("Ethereum", "ETH/KRW", cryptos["Ethereum"], batch_data, fmt="{:,.0f}", reference_text="기준: 전일 종가 (UTC 0시)", show_chart=show_charts, show_tech=show_tech)

    # --- [Quant Lab] 고급 분석 섹션 ---
    if not simple_mode and (show_heatmap or show_monte):
        st.markdown("<div class='quant-header'>Quant Lab (Advanced Analysis)</div>", unsafe_allow_html=True)
        
        close_df = pd.DataFrame()
        for t_name, t_code in {**indices, **currencies, **cryptos}.items():
            try:
                if isinstance(batch_data.columns, pd.MultiIndex):
                    series = batch_data[t_code]['Close']
                else:
                    series = batch_data['Close']
                close_df[t_name] = series
            except:
                pass
        
        close_df = close_df.fillna(method='ffill').fillna(method='bfill')

        q_col1, q_col2 = st.columns([1, 1])

        # 1. 상관관계 히트맵
        if show_heatmap:
            with q_col1:
                st.subheader("자산 간 상관관계 히트맵 (Correlation Matrix)")
                corr_matrix = close_df.corr()
                fig_corr = px.imshow(corr_matrix, text_auto=True, color_continuous_scale='RdBu_r', aspect="auto")
                fig_corr.update_layout(template="plotly_dark", height=400)
                st.plotly_chart(fig_corr, use_container_width=True)

        # 2. 몬테카를로 시뮬레이션
        if show_monte:
            with q_col2:
                st.subheader("몬테카를로 시뮬레이션 (Future Price Path)")
                target_asset = st.selectbox("시뮬레이션 대상 자산 선택", list(cryptos.keys()) + list(indices.keys()))
                target_code = {**indices, **currencies, **cryptos}[target_asset]
                
                if isinstance(batch_data.columns, pd.MultiIndex):
                    sim_data = batch_data[target_code]
                else:
                    sim_data = batch_data
                
                sim_res = run_monte_carlo(sim_data)
                
                if sim_res is not None:
                    fig_sim = go.Figure()
                    for c in sim_res.columns:
                        fig_sim.add_trace(go.Scatter(x=sim_res.index, y=sim_res[c], mode='lines', 
                                                     line=dict(width=1, color='rgba(100, 200, 255, 0.3)'), showlegend=False))
                    
                    fig_sim.update_layout(
                        title=f"{target_asset}: 향후 30일 시나리오 (50회 반복)",
                        template="plotly_dark", height=350,
                        yaxis_title="Price Forecast"
                    )
                    st.plotly_chart(fig_sim, use_container_width=True)

    # --- 자동 새로고침 ---
    if auto_refresh:
        for i in range(10, 0, -1):
            status_placeholder.caption(f"{i}초 후 업데이트...")
            time.sleep(1)
        st.cache_data.clear()
        st.rerun()
    else:
        status_placeholder.empty()

if __name__ == "__main__":
    main()