import os
import requests
import re
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from supabase import create_client, Client
import yfinance as yf # ★ 검증용으로 추가

# 1. 환경변수 로드
load_dotenv()
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

def find_correct_ticker(code):
    """
    ★ [핵심 기능] 코스피(.KS)인지 코스닥(.KQ)인지 자동 판별
    """
    # 1. 코스피(.KS)라고 가정하고 찔러보기
    ks_ticker = f"{code}.KS"
    try:
        if yf.Ticker(ks_ticker).fast_info.last_price:
            return ks_ticker
    except: pass
    
    # 2. 안 되면 코스닥(.KQ)으로 찔러보기
    kq_ticker = f"{code}.KQ"
    try:
        if yf.Ticker(kq_ticker).fast_info.last_price:
            return kq_ticker
    except: pass
    
    # 둘 다 안 되면 그냥 원본 반환 (나중에라도 수동 확인용)
    return ks_ticker

def get_trending_stocks(limit=5):
    """
    네이버 금융 '실시간 검색 상위' 수집 + 티커 자동 보정
    """
    print(f"📡 [Scanner] 시장 트렌드 감시 시작 (네이버 금융)...")
    url = "https://finance.naver.com/sise/lastsearch2.naver"
    trending = []
    
    try:
        res = requests.get(url, timeout=5)
        soup = BeautifulSoup(res.text, "html.parser")
        rows = soup.select(".type_5 tr")
        
        for row in rows:
            title_tag = row.select_one("a.tltle")
            if title_tag:
                name = title_tag.get_text().strip()
                href = title_tag['href']
                code_match = re.search(r'code=(\d+)', href)
                
                if code_match:
                    raw_code = code_match.group(1)
                    
                    # ★ 여기서 검증 들어갑니다!
                    real_ticker = find_correct_ticker(raw_code)
                    
                    trending.append({"keyword": name, "ticker": real_ticker})
                    print(f"  🔥 발견(Top {len(trending)+1}): {name} -> {real_ticker} (검증완료)")
                
                if len(trending) >= limit: 
                    break
                    
    except Exception as e:
        print(f"❌ 크롤링 실패: {e}")
        
    return trending

def update_database(stock_list):
    """Supabase DB 업데이트"""
    if not SUPABASE_URL or not SUPABASE_KEY:
        print("⚠️ Supabase 키가 없습니다.")
        return

    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
    print(f"\n💾 [DB Sync] 데이터 동기화 중 ({len(stock_list)}개)...")
    
    for item in stock_list:
        keyword = item['keyword']
        ticker = item['ticker']
        
        try:
            # 1. 이미 존재하는지 확인
            res = supabase.table('keywords').select("*").eq('keyword', keyword).execute()
            
            if res.data:
                # 존재하면 깨우기
                existing_id = res.data[0]['id']
                supabase.table('keywords').update({'is_active': True}).eq('id', existing_id).execute()
                print(f"  ✅ [Wake Up] '{keyword}' 활성화")
            else:
                # 없으면 신규 등록
                supabase.table('keywords').insert({
                    "keyword": keyword,
                    "ticker": ticker, 
                    "is_active": True
                }).execute()
                print(f"  ✨ [New] '{keyword}' ({ticker}) 등록 완료")
                
        except Exception as e:
            print(f"  ❌ Error: {e}")

if __name__ == "__main__":
    # 상위 5개 정도 넉넉하게 스캔
    hot_stocks = get_trending_stocks(limit=30)
    
    if hot_stocks:
        update_database(hot_stocks)
    else:
        print("🤔 특이 사항 없음")