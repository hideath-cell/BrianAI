import streamlit as st
import pandas as pd
import yfinance as yf
import os
from dotenv import load_dotenv
from supabase import create_client, Client

# 환경변수 로드
load_dotenv()

# DB 연결 (싱글톤 패턴)
@st.cache_resource
def init_connection():
    try:
        # Streamlit Cloud와 로컬 환경 모두 지원
        url = os.environ.get("SUPABASE_URL") or st.secrets["SUPABASE_URL"]
        key = os.environ.get("SUPABASE_KEY") or st.secrets["SUPABASE_KEY"]
    except:
        url = os.environ.get("SUPABASE_URL")
        key = os.environ.get("SUPABASE_KEY")

    if not url or not key: return None
    return create_client(url, key)

# 기술적 지표 계산
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
@st.cache_data(ttl=600)
def fetch_stock_data(ticker):
    if not ticker: return None
    try:
        df = yf.download(ticker, period="3mo", progress=False)
        if df.empty: return None
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)

        current_price = df['Close'].iloc[-1]
        prev_price = df['Close'].iloc[-2]
        change_pct = ((current_price - prev_price) / prev_price) * 100
        rsi, disparity = calculate_indicators(df)
        
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