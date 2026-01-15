import importlib
import sys

required_libraries = [
    "streamlit", "pandas", "yfinance", "supabase", "dotenv",
    "requests", "bs4", "newspaper", "trafilatura", "google.genai"
]

print("🔍 Brian AI 환경 검증 시작...\n")
missing = []

for lib in required_libraries:
    try:
        importlib.import_module(lib)
        print(f"✅ {lib:<15} : 설치됨")
    except ImportError:
        print(f"❌ {lib:<15} : 없음 (설치 필요)")
        missing.append(lib)

print("-" * 30)
if missing:
    print(f"🚨 오류: {len(missing)}개의 라이브러리가 없습니다.")
    print(f"👉 실행하세요: pip install -r requirements.txt")
else:
    print("🎉 모든 라이브러리가 정상입니다!")