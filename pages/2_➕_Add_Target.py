import streamlit as st
import time
import sys, os

# 1. 페이지 설정 (이게 제일 먼저 실행되어야 화면이 뜹니다)
st.set_page_config(page_title="Add Target", page_icon="➕")

st.title("➕ 감시 종목 추가")

# 2. 모듈 가져오기 (안전장치 추가)
try:
    # 상위 폴더(BrianAI)를 경로에 추가해야 utils.py를 찾을 수 있음
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from utils import init_connection
except ImportError as e:
    st.error(f"🚨 시스템 오류: 필수 파일을 찾을 수 없습니다.\n({e})")
    st.stop()

# 3. DB 연결 시도
supabase = init_connection()

# 4. 연결 상태에 따른 화면 분기
if not supabase:
    st.error("❌ Supabase DB 연결 실패")
    st.warning("Dashboard 페이지에서 에러 메시지를 확인했나요? .env 파일을 확인해주세요.")
else:
    # --- 정상 화면 ---
    st.caption("새로운 감시 대상을 시스템에 등록합니다.")
    st.info("💡 팁: '티커'를 입력하면 주가 정보가, 입력하지 않으면 뉴스만 수집됩니다.")

    with st.form("add_form"):
        col1, col2 = st.columns(2)
        with col1:
            kw = st.text_input("키워드 (필수)", placeholder="예: 삼성전자, 엔비디아")
        with col2:
            tk = st.text_input("티커 (선택)", placeholder="예: 005930.KS, NVDA")
        
        fix = st.checkbox("고정 관심 종목으로 등록 (체크 해제 시 트렌드로 분류)", value=True)
        
        submitted = st.form_submit_button("등록하기", type="primary")
        
        if submitted:
            if not kw:
                st.error("⚠️ 키워드는 필수 입력 항목입니다.")
            else:
                try:
                    # 데이터 전송
                    supabase.table('keywords').insert({
                        "keyword": kw,
                        "ticker": tk if tk else None,
                        "is_active": True,
                        "is_fixed": fix
                    }).execute()
                    
                    st.success(f"✅ '{kw}' 등록 성공!")
                    time.sleep(1)
                    st.rerun() # 새로고침
                    
                except Exception as e:
                    st.error(f"등록 실패: {e}")