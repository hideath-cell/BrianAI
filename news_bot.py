import os
import sys
import requests
import urllib.parse
from bs4 import BeautifulSoup
from newspaper import Article
from google import genai
from dotenv import load_dotenv
import trafilatura
import time
import datetime
import yfinance as yf
from supabase import create_client, Client

# 1. 환경변수 및 키 로드
load_dotenv()
TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
GEMINI_API_KEY = os.environ.get("GOOGLE_API_KEY")
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

# 2. Supabase 연결
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY) if SUPABASE_URL and SUPABASE_KEY else None

def send_telegram(text):
    if not TOKEN or not CHAT_ID: return
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    data = {"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML", "disable_web_page_preview": "true"}
    try:
        requests.post(url, data=data)
    except Exception as e:
        print(f"전송 실패: {e}")

def get_db_data():
    """
    ★ DB에서 '활성화된(is_active=True)' 키워드만 가져오기
    """
    print("📡 [Supabase] 브리핑 대상 조회 중...")
    if not supabase:
        print("❌ Supabase 연결 불가")
        return [], {}

    try:
        response = supabase.table('keywords').select("*").eq('is_active', True).execute()
        rows = response.data
        
        active_keywords = []
        ticker_map = {}
        
        print(f"📋 총 {len(rows)}개의 브리핑 대상을 찾았습니다.")
        for item in rows:
            word = item.get('keyword')
            ticker = item.get('ticker')
            if word:
                active_keywords.append(word)
                if ticker: ticker_map[word] = ticker
                
        return active_keywords, ticker_map
    except Exception as e:
        print(f"❌ DB 조회 실패: {e}")
        return [], {}

def get_stock_info(keyword, ticker_map):
    """주가 정보 조회"""
    ticker = ticker_map.get(keyword)
    if not ticker: return ""

    try:
        stock = yf.Ticker(ticker)
        info = stock.fast_info
        
        price = info.last_price
        if price is None: return "" # 데이터 없음
        
        prev_close = info.previous_close
        day_high = info.day_high
        day_low = info.day_low
        year_high = info.year_high
        year_low = info.year_low
        
        # 거래량
        current_volume = info.last_volume
        avg_volume_3mo = info.three_month_average_volume

        change = price - prev_close
        change_pct = (change / prev_close) * 100
        
        if change > 0: emoji, sign = "🔺", "+"
        elif change < 0: emoji, sign = "🦋", ""
        else: emoji, sign = "➖", ""

        is_krw = ".KS" in ticker or ".KQ" in ticker or ticker == "KRW=X"
        currency = "원" if is_krw else "$"

        def fmt(num):
            if num is None: return "-"
            if is_krw: return f"{num:,.0f}"
            return f"{num:,.2f}"

        # 거래량 분석
        vol_str = "-"
        if current_volume and avg_volume_3mo and avg_volume_3mo > 0:
            vol_ratio = (current_volume / avg_volume_3mo) * 100
            if vol_ratio >= 200: vol_stat = f"🔥폭발"
            elif vol_ratio >= 120: vol_stat = f"🔺급증"
            elif vol_ratio <= 70: vol_stat = f"🦋소강"
            else: vol_stat = f"➖평이"
            
            if current_volume > 1_000_000: v_disp = f"{current_volume/1_000_000:.1f}M"
            else: v_disp = f"{current_volume/1_000:.1f}K"
            vol_str = f"{v_disp} [{vol_stat} {vol_ratio:.0f}%]"

        result = f"\n💰 <b>{keyword} 시장 현황</b>\n"
        result += f"{'-'*30}\n"
        result += f"<b>현재가: {fmt(price)}{currency}</b> ({emoji} {sign}{change_pct:.2f}%)\n"
        result += f"일변동: {fmt(day_low)} ~ {fmt(day_high)}\n"
        result += f"52주폭: {fmt(year_low)} ~ {fmt(year_high)}\n"
        result += f"거래량: <b>{vol_str}</b>\n\n"
        return result

    except Exception as e:
        print(f"주가 조회 실패({keyword}): {e}")
        return ""

# (뉴스 수집 및 AI 요약 함수들 - 기존과 동일하지만 전체 코드 유지를 위해 포함)
def get_final_url(url):
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        return requests.head(url, headers=headers, allow_redirects=True, timeout=3).url
    except: return url

def get_article_content(url):
    if "news.google.com" in url: url = get_final_url(url)
    try:
        d = trafilatura.fetch_url(url)
        if d: 
            t = trafilatura.extract(d, include_comments=False, include_tables=False)
            if t and len(t)>50: return t[:1000], "Trafilatura"
    except: pass
    try:
        a = Article(url, language='ko')
        a.download(); a.parse()
        if len(a.text)>50: return a.text[:1000], "Newspaper"
    except: pass
    return None, "Fail"

def fetch_rss_items(keyword):
    encoded = urllib.parse.quote(keyword)
    items = []
    # 구글, 빙 병합
    urls = [
        f"https://news.google.com/rss/search?q={encoded}&hl=ko&gl=KR&ceid=KR:ko",
        f"https://www.bing.com/news/search?q={encoded}&format=rss"
    ]
    for url in urls:
        try:
            res = requests.get(url, timeout=3)
            soup = BeautifulSoup(res.text, "xml")
            for item in soup.find_all("item")[:3]: # 각 엔진별 상위 3개
                snip = BeautifulSoup(item.description.get_text(), "html.parser").get_text() if item.description else ""
                items.append({"title": item.title.get_text(), "link": item.link.get_text(), "snippet": snip})
        except: pass
    return items

def get_gemini_summary(keyword, text_data):
    if not GEMINI_API_KEY: return "⚠️ API 키 없음"
    try:
        client = genai.Client(api_key=GEMINI_API_KEY)
        prompt = f"""
        너는 전문 금융 비서야. '{keyword}' 뉴스 데이터를 보고 브리핑해줘.
        [Part 1: ⚡ 3줄 핵심] 이모지 필수, 숫자(금액/%)는 <b>태그로 굵게.
        [Part 2: 📝 상세 흐름] 300자 내외, 해요체.
        [뉴스 데이터] {text_data}
        """
        return client.models.generate_content(model="gemini-2.0-flash", contents=prompt).text
    except Exception as e: return f"AI Error: {e}"

def process_keyword(keyword, ticker_map):
    print(f"🚀 '{keyword}' 분석 중...")
    today = datetime.datetime.now().strftime("%y/%m/%d")
    
    stock_msg = get_stock_info(keyword, ticker_map)
    news_items = fetch_rss_items(keyword)
    
    if not news_items: 
        print("  - 뉴스 없음")
        return

    llm_input = []
    for idx, item in enumerate(news_items):
        if idx < 4: # 상위 4개만 정독
            c, _ = get_article_content(item['link'])
            t = c if c else item['snippet']
        else: t = item['snippet']
        llm_input.append(f"제목: {item['title']}\n내용: {t}\n")

    print(f"  🤖 AI 요약 중...")
    summary = get_gemini_summary(keyword, "\n".join(llm_input))
    
    msg = f"🔥 <b>[{today}] {keyword} 브리핑</b> 🔥\n"
    msg += stock_msg
    msg += f"{summary}\n\n"
    msg += f"<b>📰 주요 뉴스</b>\n"
    for i, item in enumerate(news_items[:4], 1):
        ct = item['title'].replace("<", "").replace(">", "")
        msg += f"{i}. <a href='{item['link']}'>{ct}</a>\n"
        
    send_telegram(msg)
    print(f"✅ 전송 완료")

if __name__ == "__main__":
    target_list, ticker_mapping = get_db_data()
    
    if not target_list:
        print("💤 활성화된 키워드가 없습니다.")
    else:
        for word in target_list:
            process_keyword(word, ticker_mapping)
            time.sleep(3)