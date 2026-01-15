import streamlit as st
import pandas as pd
import sys, os

st.set_page_config(page_title="Dashboard", page_icon="📊", layout="wide")

# 1. 모듈 가져오기 디버깅
try:
    # 상위 폴더 경로 추가
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from utils import init_connection, fetch_stock_data, get_links
    import bot
except ImportError as e:
    st.error(f"🚨 모듈을 찾을 수 없습니다! utils.py나 bot.py가 BrianAI 폴더에 있는지 확인하세요.\n에러 내용: {e}")
    st.stop() # 여기서 멈춤

st.title("📊 Brian AI Dashboard")

# 2. DB 연결 시도
with st.spinner("DB에 연결 중입니다..."):
    supabase = init_connection()

# 3. 사이드바: 봇 컨트롤
with st.sidebar:
    st.header("🎮 Bot Control")
    # DB 연결이 안 돼도 버튼은 보이게 (테스트용)
    if st.button("🚀 브리핑 시작 (Run Batch)", type="primary"):
        try:
            with st.status("Brian AI가 작동 중입니다...", expanded=True) as status:
                logs = bot.run_batch_briefing()
                for log in logs:
                    st.write(log)
                status.update(label="작업 완료!", state="complete", expanded=False)
            st.success("브리핑 전송 완료")
        except Exception as e:
            st.error(f"봇 실행 중 에러 발생: {e}")

# 4. 메인: 현황판
if supabase:
    # ... (기존 정상 로직) ...
    try:
        def toggle(id, status):
            supabase.table('keywords').update({'is_active': not status}).eq('id', id).execute()
            st.rerun()
        
        def delete(id):
            supabase.table('keywords').delete().eq('id', id).execute()
            st.rerun()

        # 데이터 가져오기
        response = supabase.table('keywords').select("*").order('id', desc=True).execute()
        df = pd.DataFrame(response.data)

        if not df.empty:
            tab1, tab2 = st.tabs(["🔒 Fixed Interest", "🔥 Trending Now"])

            def render_list(target_df, key_prefix):
                if target_df.empty:
                    st.info("데이터가 없습니다.")
                    return
                
                for _, row in target_df.iterrows():
                    data = fetch_stock_data(row['ticker'])
                    
                    label = f"**{row['keyword']}**"
                    if data:
                        color = "🔴" if data['change'] > 0 else "🔵"
                        rsi_val = data['rsi'] if data['rsi'] is not None else 50
                        rsi_txt = "🔥과열" if rsi_val >= 70 else "❄️침체" if rsi_val <= 30 else "중립"
                        label += f" | {data['price']:,.0f} ({color} {data['change']:.1f}%) | RSI: {rsi_val:.0f}({rsi_txt})"
                    else:
                        label += " | ⏳ 데이터 로딩 중..."
                    
                    with st.expander(label):
                        c1, c2 = st.columns([3, 1])
                        with c1:
                            if data and 'history' in data: 
                                st.line_chart(data['history']['Close'], height=200)
                        with c2:
                            s_link, n_link = get_links(row['keyword'], row['ticker'])
                            st.markdown(f"[금융정보]({s_link}) | [뉴스검색]({n_link})")
                            st.divider()
                            on = st.toggle("Active", value=row['is_active'], key=f"{key_prefix}_{row['id']}")
                            if on != row['is_active']: toggle(row['id'], row['is_active'])
                            if st.button("Delete", key=f"del_{key_prefix}_{row['id']}"): delete(row['id'])

            with tab1: render_list(df[df['is_fixed']==True] if 'is_fixed' in df.columns else df, "fix")
            with tab2: render_list(df[df['is_fixed']==False] if 'is_fixed' in df.columns else pd.DataFrame(), "trd")
        else:
            st.info("데이터베이스에 등록된 종목이 없습니다. 'Add Target' 메뉴에서 추가해주세요.")

    except Exception as e:
        st.error(f"데이터를 불러오는 중 에러가 발생했습니다:\n{e}")

else: 
    # ★ 여기가 핵심입니다! 연결 실패 시 에러 보여주기
    st.error("❌ Supabase DB 연결에 실패했습니다.")
    st.warning("1. .env 파일이 BrianAI 폴더 안에 있는지 확인하세요.")
    st.warning("2. SUPABASE_URL과 KEY가 정확한지 확인하세요.")