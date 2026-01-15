import streamlit as st
import pandas as pd
import yfinance as yf
import os
from dotenv import load_dotenv
from supabase import create_client, Client
import time
import datetime

# 1. 페이지 설정
st.set_page_config(page_title="News Bot Dashboard", page_icon="📈", layout="wide")

# 2. 환경변수 및 DB 연결
load_dotenv()
try:
    SUPABASE_URL = st.secrets["SUPABASE_URL"]
    SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
except Exception:
    SUPABASE_URL = os.environ.get("SUPABASE_URL")
    SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

@st.cache_resource
def init_connection():
    if not SUPABASE_URL or not SUPABASE_KEY: return None
    return create_client(SUPABASE_URL, SUPABASE_KEY)

supabase = init_connection()

# --- 기술적 지표 계산 함수 ---
def calculate_indicators(df):
    """
    RSI(14)와 이동평균(20) 괴리율 계산
    """
    if len(df) < 20: return None, None # 데이터 부족

    # 1. RSI 계산
    delta = df['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    
    # 2. 이동평균선(20일) 및 괴리율
    ma20 = df['Close'].rolling(window=20).mean()
    current_price = df['Close'].iloc[-1]
    last_ma20 = ma20.iloc[-1]
    disparity = ((current_price - last_ma20) / last_ma20) * 100 # % 단위

    return rsi.iloc[-1], disparity

# --- 데이터 가져오기 (캐싱) ---
@st.cache_data(ttl=600)
def fetch_stock_data(ticker):
    """
    yfinance에서 3달치 데이터 가져오기 (지표 계산용)
    """
    if not ticker: return None
    try:
        df = yf.download(ticker, period="3mo", progress=False)
        if df.empty: return None
        
        # 멀티인덱스 컬럼 처리 (yfinance 최신버전 이슈 대응)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        current_price = df['Close'].iloc[-1]
        prev_price = df['Close'].iloc[-2]
        change_pct = ((current_price - prev_price) / prev_price) * 100
        
        rsi, disparity = calculate_indicators(df)
        
        return {
            "price": current_price,
            "change": change_pct,
            "rsi": rsi,
            "disparity": disparity,
            "history": df # 차트 그리기용 데이터프레임
        }
    except Exception as e:
        return None

def get_db_data():
    if not supabase: return pd.DataFrame()
    response = supabase.table('keywords').select("*").order('id', desc=True).execute()
    return pd.DataFrame(response.data)

def toggle_status(row_id, current_status):
    supabase.table('keywords').update({'is_active': not current_status}).eq('id', row_id).execute()
    st.rerun()

def delete_keyword(row_id):
    supabase.table('keywords').delete().eq('id', row_id).execute()
    st.rerun()

def get_links(keyword, ticker):
    news_url = f"https://search.naver.com/search.naver?where=news&query={keyword}&sm=tab_opt&sort=1"
    if ticker and (".KS" in ticker or ".KQ" in ticker):
        code = ticker.split('.')[0]
        stock_url = f"https://finance.naver.com/item/main.naver?code={code}"
    elif ticker:
        stock_url = f"https://finance.yahoo.com/quote/{ticker}"
    else:
        stock_url = news_url
    return stock_url, news_url

# ================= 메인 UI =================

with st.sidebar:
    st.title("🤖 뉴스 봇 관제소")
    menu = st.radio("메뉴", ["📈 종합 현황판", "➕ 종목 추가"])

if menu == "📈 종합 현황판":
    st.title("📈 주식 종합 현황판")
    
    if supabase:
        df = get_db_data()
        
        if not df.empty:
            tab1, tab2 = st.tabs(["🔒 내 관심 종목 (Fixed)", "🔥 실시간 트렌드 (Auto)"])
            
            # --- 공통 렌더링 함수 ---
            def render_stock_list(target_df, section_name):
                if target_df.empty:
                    st.info(f"{section_name} 종목이 없습니다.")
                    return

                for index, row in target_df.iterrows():
                    ticker = row.get('ticker')
                    keyword = row['keyword']
                    
                    # 데이터 로딩
                    data = fetch_stock_data(ticker) if ticker else None
                    
                    # --- 요약 카드 ---
                    label_text = f"**{keyword}**"
                    if data:
                        price_fmt = f"{data['price']:,.0f}" if ".KS" in str(ticker) or ".KQ" in str(ticker) else f"{data['price']:.2f}"
                        emoji = "🔺" if data['change'] > 0 else "🦋"
                        
                        rsi_val = data['rsi'] if data['rsi'] else 0
                        rsi_status = "과매수" if rsi_val >= 70 else "과매도" if rsi_val <= 30 else "중립"
                        
                        disp_val = data['disparity'] if data['disparity'] else 0
                        disp_emoji = "🔥과열" if disp_val > 5 else "❄️침체" if disp_val < -5 else "평이"

                        label_text += f" | {price_fmt} ({emoji} {data['change']:.2f}%) | RSI: {rsi_val:.0f} ({rsi_status}) | 이격: {disp_emoji}"
                    else:
                        label_text += " | ⏳ 로딩중/티커없음"

                    with st.expander(label_text, expanded=False):
                        c1, c2 = st.columns([3, 1])
                        
                        with c1:
                            if data and data['history'] is not None:
                                st.caption("📉 최근 3개월 주가 흐름")
                                st.line_chart(data['history']['Close'], height=250)
                            else:
                                st.write("차트 데이터 없음")
                                
                        with c2:
                            st.write("#### 관리 메뉴")
                            # ★ 수정된 부분: 변수명 일치 (stock_url)
                            stock_url, news_url = get_links(keyword, ticker)
                            st.markdown(f"👉 [금융 정보 이동]({stock_url})")
                            st.markdown(f"👉 [관련 뉴스 검색]({news_url})")
                            
                            st.markdown("---")
                            is_on = st.toggle("감시 봇 작동", value=row['is_active'], key=f"tg_{row['id']}")
                            if is_on != row['is_active']:
                                toggle_status(row['id'], row['is_active'])
                                
                            if section_name == "Fixed":
                                if st.button("삭제", key=f"del_{row['id']}"):
                                    delete_keyword(row['id'])

            # [Tab 1] Fixed 렌더링
            with tab1:
                # is_fixed 컬럼 체크
                if 'is_fixed' in df.columns:
                    fixed_rows = df[df['is_fixed'] == True]
                else:
                    fixed_rows = df
                render_stock_list(fixed_rows, "Fixed")
                
            # [Tab 2] Trending 렌더링
            with tab2:
                if 'is_fixed' in df.columns:
                    trend_rows = df[df['is_fixed'] == False]
                else:
                    trend_rows = pd.DataFrame()
                render_stock_list(trend_rows, "Trending")

elif menu == "➕ 종목 추가":
    st.title("➕ 종목 추가")
    with st.form("add"):
        kw = st.text_input("종목명")
        tk = st.text_input("티커 (예: 005930.KS, TSLA)")
        fix = st.checkbox("고정 종목으로 등록", value=True)
        if st.form_submit_button("등록"):
            if kw:
                supabase.table('keywords').insert({"keyword":kw, "ticker":tk if tk else None, "is_active":True, "is_fixed":fix}).execute()
                st.success("등록 완료!")
                time.sleep(1)
                st.rerun()