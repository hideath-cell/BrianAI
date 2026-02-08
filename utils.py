import streamlit as st
import pandas as pd
import yfinance as yf
import os
import sys
import logging
from dotenv import load_dotenv
from supabase import create_client, Client

# Streamlit 경고 메시지 억제 (터미널 실행 시)
try:
    import streamlit as st
    from streamlit.runtime.scriptrunner import get_script_run_ctx
    if not get_script_run_ctx():
        logging.getLogger("streamlit").setLevel(logging.ERROR)
except ImportError:
    pass

# 윈도우 터미널 한글 깨짐 방지
def fix_encoding():
    if sys.stdout.encoding != 'utf-8':
        try:
            sys.stdout.reconfigure(encoding='utf-8')
        except AttributeError:
            import io
            sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# Streamlit 캐싱 안전하게 적용 (터미널 실행 시 경고 방지)
def safe_cache_resource(func):
    try:
        from streamlit.runtime.scriptrunner import get_script_run_ctx
        if get_script_run_ctx():
            return st.cache_resource(func)
    except: pass
    return func

def safe_cache_data(**kwargs):
    def decorator(func):
        try:
            from streamlit.runtime.scriptrunner import get_script_run_ctx
            if get_script_run_ctx():
                return st.cache_data(**kwargs)(func)
        except: pass
        return func
    return decorator

# 환경변수 로드
load_dotenv()

# DB 연결 (싱글톤 패턴)
@safe_cache_resource
def init_connection():
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")
    
    # Streamlit Cloud/Secrets 지원
    if not url or not key:
        try:
            url = st.secrets["SUPABASE_URL"]
            key = st.secrets["SUPABASE_KEY"]
        except: pass

    if not url or not key: return None
    return create_client(url, key)

# 한국 종목 티커 보정 (.KS / .KQ)
def find_correct_ticker(code):
    """
    코스피(.KS)인지 코스닥(.KQ)인지 판별
    """
    if not code or not str(code).isdigit():
        return code
        
    # 1. 코스피(.KS) 시도
    ks_ticker = f"{code}.KS"
    try:
        if yf.Ticker(ks_ticker).fast_info.last_price:
            return ks_ticker
    except: pass
    
    # 2. 코스닥(.KQ) 시도
    kq_ticker = f"{code}.KQ"
    try:
        if yf.Ticker(kq_ticker).fast_info.last_price:
            return kq_ticker
    except: pass
    
    return ks_ticker

# 기술적 지표 계산 (기본형 - app.py 호환 유지)
def calculate_indicators(df):
    if len(df) < 20: return None, None
    delta = df['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    
    ma20 = df['Close'].rolling(window=20).mean()
    current_price = df['Close'].iloc[-1]
    disparity = ((current_price - ma20.iloc[-1]) / ma20.iloc[-1]) * 100
    return rsi.iloc[-1], disparity

# 주가 데이터 가져오기 (캐싱 적용)
@safe_cache_data(ttl=600)
def fetch_stock_data(ticker, period="3mo"):
    if not ticker: return None
    try:
        df = yf.download(ticker, period=period, progress=False)
        if df.empty: return None
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)

        current_price = df['Close'].iloc[-1]
        
        # 데이터가 2개 미만인 경우 (신규 상장 등) 예외 처리
        if len(df) >= 2:
            prev_price = df['Close'].iloc[-2]
            change_pct = ((current_price - prev_price) / prev_price) * 100
            rsi, disparity = calculate_indicators(df)
        else:
            change_pct = 0.0
            rsi, disparity = None, None
        
        return {
            "price": current_price, "change": change_pct,
            "rsi": rsi, "disparity": disparity, "history": df
        }
    except: return None

# 링크 생성
def get_links(keyword, ticker):
    news_url = f"https://search.naver.com/search.naver?where=news&query={keyword}&sm=tab_opt&sort=1"
    stock_url = news_url
    if ticker:
        if ".KS" in ticker or ".KQ" in ticker:
            code = ticker.split('.')[0]
            stock_url = f"https://finance.naver.com/item/main.naver?code={code}"
        else:
            stock_url = f"https://finance.yahoo.com/quote/{ticker}"
    return stock_url, news_url
