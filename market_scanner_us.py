import requests
from bs4 import BeautifulSoup
import time

# 한글 이름 매핑 (주요 종목은 한글로 검색되게)
NAME_MAP = {
    "NVDA": "엔비디아", "TSLA": "테슬라", "AAPL": "애플", "MSFT": "마이크로소프트",
    "AMZN": "아마존", "GOOGL": "구글", "GOOG": "구글", "META": "메타",
    "NFLX": "넷플릭스", "AMD": "AMD", "INTC": "인텔", "COIN": "코인베이스",
    "PLTR": "팔란티어", "MSTR": "마이크로스트래티지"
}

def get_us_trending_stocks(limit=10):
    """
    야후 파이낸스 Trending Tickers 크롤링 (화면 출력용)
    """
    print(f"📡 [미국] 야후 파이낸스 접속 중...")
    
    # 봇 차단 방지용 헤더 (브라우저인 척 속임)
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    url = "https://finance.yahoo.com/trending-tickers"
    
    trending = []
    
    try:
        res = requests.get(url, headers=headers, timeout=10)
        if res.status_code != 200:
            print(f"❌ 접속 실패: 상태 코드 {res.status_code}")
            return []

        soup = BeautifulSoup(res.text, "html.parser")
        
        # 야후 파이낸스 테이블 찾기
        # (구조가 자주 바뀌어서 가장 일반적인 'tr' 태그 검색 방식을 사용)
        rows = soup.find_all("tr")
        
        if not rows:
            print("❌ 데이터를 찾을 수 없습니다. (웹사이트 구조 변경 가능성)")
            return []

        print(f"🔍 데이터 추출 및 필터링 중...\n")
        
        count = 0
        for row in rows:
            # 보통 첫 번째 td에 티커가 들어있음
            cols = row.find_all("td")
            if len(cols) > 2: # 데이터가 있는 행만
                ticker = cols[0].get_text().strip()
                
                # 1. 이상한 티커 거르기 (지수^, 옵션., 선물= 등)
                if any(x in ticker for x in ["^", ".", "="]): 
                    continue
                
                # 2. 이름 매핑 (없으면 티커 그대로)
                keyword = NAME_MAP.get(ticker, ticker)
                
                # 3. 현재 가격 (세 번째 컬럼, 참고용)
                price = cols[2].get_text().strip()
                
                # 4. 등락률 (다섯 번째 컬럼)
                change_pct = cols[4].get_text().strip()

                trending.append({
                    "ticker": ticker,
                    "keyword": keyword,
                    "price": price,
                    "change": change_pct
                })
                
                count += 1
                if count >= limit: break
                
    except Exception as e:
        print(f"❌ 에러 발생: {e}")
        
    return trending

if __name__ == "__main__":
    # 실행 부: 결과를 화면에 예쁘게 출력
    results = get_us_trending_stocks(limit=5)
    
    print("-" * 50)
    print("🇺🇸 미국 시장 실시간 트렌드 (Top 5)")
    print("-" * 50)
    
    if results:
        for idx, item in enumerate(results, 1):
            print(f"{idx}. {item['keyword']} ({item['ticker']})")
            print(f"   💰 가격: ${item['price']} | 📈 변동: {item['change']}")
            print(f"   👉 DB 저장 키워드: {item['keyword']}")
            print("-" * 30)
    else:
        print("🤔 데이터를 가져오지 못했습니다.")