import streamlit as st
import pandas as pd
import yfinance as yf
import os
import time
import datetime
from dotenv import load_dotenv
from supabase import create_client, Client
from quant_analyzer import analyze_stock

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

# --- UI 헬퍼 함수 ---
def get_indicator_status(name, value):
    """지표별 아이콘 및 상태 텍스트 반환"""
    if value is None: return "⚪", "데이터부족"
    
    if name == "RSI":
        if value >= 70: return "🔥", "과매수"
        if value <= 30: return "❄️", "과매도"
        return "⚖️", "중립"
    elif name == "MFI":
        if value >= 80: return "💰", "유입강함"
        if value <= 20: return "💸", "이탈주의"
        return "⚖️", "보통"
    elif name == "MACD":
        if value > 0: return "📈", "상승강화"
        return "📉", "하락지속"
    elif name == "BB":
        if value > 0.9: return "🚀", "상단돌파"
        if value < 0.1: return "🛡️", "하단지지"
        return "📦", "박스권"
    elif name == "Stoch":
        if value > 80: return "⚠️", "단기과열"
        if value < 20: return "☘️", "단기저점"
        return "⚖️", "중립"
    elif name == "Volume":
        if value > 250: return "💥", "수급폭발"
        if value < 50: return "💤", "거래침체"
        return "✅", "보통"
    return "", ""

# --- 데이터 가져오기 (캐싱) ---
@st.cache_data(ttl=600)
def fetch_stock_data(ticker):
    """
    yfinance에서 1년치 데이터 가져오기 및 퀀트 분석 엔진 연동
    """
    if not ticker: return None
    try:
        df = yf.download(ticker, period="1y", progress=False)
        if df.empty: return None
        
        # 멀티인덱스 컬럼 처리
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        # 퀀트 분석 엔진 호출
        metrics = analyze_stock(df)
        
        current_price = df['Close'].iloc[-1]
        prev_price = df['Close'].iloc[-2] if len(df) >= 2 else current_price
        change_pct = ((current_price - prev_price) / prev_price) * 100 if len(df) >=2 else 0
        
        return {
            "price": current_price,
            "change": change_pct,
            "metrics": metrics,
            "history": df
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
                    
                    # --- 요약 카드 라벨 생성 ---
                    label_text = f"**{keyword}**"
                    if data:
                        m = data['metrics']
                        price_fmt = f"{data['price']:,.0f}" if ticker and (".KS" in str(ticker) or ".KQ" in str(ticker)) else f"{data['price']:.2f}"
                        emoji = "🔺" if data['change'] > 0 else "🦋"
                        
                        # 요약 지표 아이콘
                        rsi_icon, _ = get_indicator_status("RSI", m['rsi'])
                        vol_icon, _ = get_indicator_status("Volume", m['volume_ratio'])
                        score_icon = "💎" if m['score'] >= 70 else "⚠️" if m['score'] <= 30 else "📉" if m['score'] < 50 else "📈"
                        
                        label_text += f" | {price_fmt} ({emoji} {data['change']:.2f}%) | {score_icon} Score: {m['score']} | {rsi_icon} RSI | {vol_icon} Vol"
                    else:
                        label_text += " | ⏳ 로딩중/티커없음"

                    with st.expander(label_text, expanded=False):
                        if not data:
                            st.warning("데이터를 가져오는 중이거나 티커가 올바르지 않습니다.")
                            continue
                            
                        m = data['metrics']
                        
                        # --- 상단 메트릭 레이아웃 ---
                        mc1, mc2, mc3, mc4 = st.columns(4)
                        mc1.metric("종합 점수", f"{m['score']}점", help="10대 지표 가중 합산 점수")
                        mc2.metric("52주 위치", f"{m['position_52w']:.1f}%", help="1년 고/저점 대비 가격 위치")
                        mc3.metric("RSI (14)", f"{m['rsi']:.1f}" if m['rsi'] else "N/A")
                        # 이격도는 metrics의 disparity 사용
                        mc4.metric("이격도 (20)", f"{m['disparity']:.1f}%" if m['disparity'] else "N/A")

                        st.markdown("---")
                        
                        # --- 상세 분석 표 & 차트 ---
                        c1, c2 = st.columns([2, 1])
                        
                        with c1:
                            st.write("#### 📊 10대 퀀트 지표 분석")
                            
                            # 데이터프레임 구성을 위한 리스트
                            q_data = []
                            # 모멘텀
                            r_i, r_s = get_indicator_status("RSI", m['rsi'])
                            q_data.append(["모멘텀", "RSI (14)", f"{m['rsi']:.1f}" if m['rsi'] else "-", f"{r_i} {r_s}"])
                            
                            m_i, m_s = get_indicator_status("MFI", m['mfi'])
                            q_data.append(["모멘텀", "MFI (14)", f"{m['mfi']:.1f}" if m['mfi'] else "-", f"{m_i} {m_s}"])
                            
                            s_i, s_s = get_indicator_status("Stoch", m['stochastic']['k'])
                            q_data.append(["모멘텀", "Stoch K", f"{m['stochastic']['k']:.1f}" if m['stochastic']['k'] else "-", f"{s_i} {s_s}"])
                            
                            # 추세
                            macd_i, macd_s = get_indicator_status("MACD", m['macd']['hist'])
                            q_data.append(["추세", "MACD Hist", f"{m['macd']['hist']:.1f}" if m['macd']['hist'] else "-", f"{macd_i} {macd_s}"])
                            q_data.append(["추세", "MA 배열", m['ma_alignment'], "추세 지속성"])
                            
                            # 변동성/기타
                            b_i, b_s = get_indicator_status("BB", m['bollinger']['pct_b'])
                            q_data.append(["변동성", "Bollinger %B", f"{m['bollinger']['pct_b']:.2f}" if m['bollinger']['pct_b'] is not None else "-", f"{b_i} {b_s}"])
                            
                            v_i, v_s = get_indicator_status("Volume", m['volume_ratio'])
                            q_data.append(["수급", "거래량 비율", f"{m['volume_ratio']:.1f}%" if m['volume_ratio'] else "-", f"{v_i} {v_s}"])

                            qt_df = pd.DataFrame(q_data, columns=["분류", "지표명", "현재값", "상태 진단"])
                            st.table(qt_df)
                            
                            # ATR 정보
                            if m['atr']:
                                st.info(f"💡 **리스크 관리**: ATR 변동폭은 **{m['atr']:,.0f}원**이며, 추천 손절가(2-ATR)는 **{m['stop_loss']:,.0f}원**입니다.")

                        with c2:
                            st.write("#### 🛠️ 관리 메뉴")
                            stock_url, news_url = get_links(keyword, ticker)
                            st.markdown(f"🔗 [네이버/야후 금융 정보]({stock_url})")
                            st.markdown(f"📰 [관련 최신 뉴스 검색]({news_url})")
                            
                            st.markdown("---")
                            is_on = st.toggle("감시 봇 작동", value=row['is_active'], key=f"tg_{row['id']}")
                            if is_on != row['is_active']:
                                toggle_status(row['id'], row['is_active'])
                                
                            if section_name == "Fixed":
                                if st.button("삭제", key=f"del_{row['id']}"):
                                    delete_keyword(row['id'])
                            
                            st.markdown("---")
                            if data['history'] is not None:
                                st.caption("📈 최근 주가 추이 (1년)")
                                st.line_chart(data['history']['Close'], height=200)

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