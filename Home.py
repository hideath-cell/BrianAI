import streamlit as st

st.set_page_config(page_title="Brian AI", page_icon="🧠", layout="wide")

st.title("🧠 Brian AI")
st.caption("Intelligence Market Watcher")
st.markdown("---")

st.markdown("""
### 👋 환영합니다.
**Brian AI**는 당신만을 위한 개인화된 시장 감시 시스템입니다.

#### 🕹️ 시스템 제어
왼쪽 사이드바에서 메뉴를 선택하세요.

* **📊 Dashboard**: 실시간 시장 현황을 확인하고, **AI 봇을 실행**합니다.
* **➕ Add Target**: 새로운 감시 대상을 시스템에 등록합니다.
""")

st.info("💡 Tip: 텔레그램 알림이 오지 않는다면 .env 파일의 토큰을 확인하세요.")