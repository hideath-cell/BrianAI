import os
import requests
import re
import sys
import pandas as pd
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from supabase import create_client, Client
import yfinance as yf
from datetime import datetime

# 윈도우 터미널 한글 깨짐 방지 (UTF-8 강제)
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError:
        # Python 3.7 미만 대응 (필요 시)
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# 1. 환경변수 로드
load_dotenv()
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

def find_correct_ticker(code):
    """
    코스피(.KS)인지 코스닥(.KQ)인지 판별
    """
    print(f"  [Ticker Check] {code}...", end=" ", flush=True)
    # 1. 코스피(.KS) 시도
    ks_ticker = f"{code}.KS"
    try:
        if yf.Ticker(ks_ticker).fast_info.last_price:
            print(f"-> [KOSPI] OK")
            return ks_ticker
    except: pass
    
    # 2. 코스닥(.KQ) 시도
    kq_ticker = f"{code}.KQ"
    try:
        if yf.Ticker(kq_ticker).fast_info.last_price:
            print(f"-> [KOSDAQ] OK")
            return kq_ticker
    except: pass
    
    print(f"-> [DEFAULT .KS]")
    return ks_ticker

def get_volatility_stocks(min_change=5.0, limit=10):
    """
    네이버 금융 '등락률 상위' 페이지에서 변동성 큰 종목 수집
    """
    print(f"\n" + "="*50)
    print(f"SCANNER: Market analysis started (Min Change: {min_change}%)")
    print("="*50)
    
    urls = [
        ("상한가 종목", "https://finance.naver.com/sise/sise_upper.naver"),
        ("상승 종목", "https://finance.naver.com/sise/sise_rise.naver"),
    ]
    
    volatile_stocks = []
    seen_codes = set()

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    for title, url in urls:
        print(f"\nPAGE: [{title}] Connecting to {url}")
        try:
            res = requests.get(url, headers=headers, timeout=10)
            if res.status_code == 200:
                print(f"  SUCCESS: Connected ({res.status_code})")
            else:
                print(f"  FAILED: Connection error ({res.status_code})")
                continue

            soup = BeautifulSoup(res.text, "html.parser")
            rows = soup.select("table.type_2 tr")
            print(f"  DATA: Found {len(rows)} rows.")
            
            row_count = 0
            for row in rows:
                title_tag = row.select_one("a.tltle")
                if not title_tag:
                    continue
                
                name = title_tag.get_text().strip()
                href = title_tag['href']
                code_match = re.search(r'code=(\d+)', href)
                
                if not code_match:
                    continue
                    
                code = code_match.group(1)
                if code in seen_codes:
                    continue

                # 등락률 추출
                tds = row.find_all("td")
                change_pct = 0.0
                for td in tds:
                    if '%' in td.get_text():
                        try:
                            change_text = td.get_text().strip().replace('%', '').replace('+', '').replace(',', '')
                            change_pct = float(change_text)
                            break
                        except: pass
                
                # 필터링 로그
                if change_pct >= min_change:
                    print(f"  MATCH: {name} ({change_pct}%)")
                    seen_codes.add(code)
                    ticker = find_correct_ticker(code)
                    volatile_stocks.append({
                        "keyword": name,
                        "ticker": ticker,
                        "change": change_pct
                    })
                    row_count += 1
                
                if len(volatile_stocks) >= limit:
                    print(f"  LIMIT: Reached target count ({limit})")
                    break
            
            print(f"  DONE: [{title}] Analysis finished ({row_count} stocks found)")

            if len(volatile_stocks) >= limit:
                break
                
        except Exception as e:
            print(f"  ERROR: {e}")

    print("\n" + "-"*50)
    print(f"SUMMARY: Found {len(volatile_stocks)} stocks total.")
    print("-"*50 + "\n")
    return volatile_stocks

def update_database(stock_list):
    """Supabase DB 업데이트 (market_scanner.py logic 기반)"""
    if not SUPABASE_URL or not SUPABASE_KEY:
        print("SKIP: Missing Supabase credentials.")
        return

    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
    print(f"\nDB_SYNC: Updating {len(stock_list)} items...")
    
    for item in stock_list:
        keyword = item['keyword']
        ticker = item['ticker']
        
        try:
            # 1. 이미 존재하는지 확인
            res = supabase.table('keywords').select("*").eq('keyword', keyword).execute()
            
            if res.data:
                # 존재하면 활성화 및 업데이트 (변동성 종목은 is_fixed를 False로 유지)
                existing_id = res.data[0]['id']
                supabase.table('keywords').update({
                    'is_active': True,
                    'is_fixed': False,
                    'ticker': ticker # 티커 업데이트
                }).eq('id', existing_id).execute()
                print(f"  UDPATE: '{keyword}'")
            else:
                # 없으면 신규 등록
                supabase.table('keywords').insert({
                    "keyword": keyword,
                    "ticker": ticker, 
                    "is_active": True,
                    "is_fixed": False
                }).execute()
                print(f"  NEW: '{keyword}' ({ticker})")
                
        except Exception as e:
            print(f"  ERR: DB Error ({keyword}): {e}")

if __name__ == "__main__":
    # 등락률 5.0% 이상인 종목 최대 15개 추출
    hot_stocks = get_volatility_stocks(min_change=5.0, limit=15)
    
    if hot_stocks:
        update_database(hot_stocks)
    else:
        print("🤔 현재 유의미한 변동성을 보이는 종목이 없습니다.")
