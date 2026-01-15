import os
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

load_dotenv()
TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
GEMINI_API_KEY = os.environ.get("GOOGLE_API_KEY")
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY) if SUPABASE_URL and SUPABASE_KEY else None

def send_telegram(text):
    if not TOKEN or not CHAT_ID: return
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    data = {"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML", "disable_web_page_preview": "true"}
    try: requests.post(url, data=data)
    except Exception as e: print(f"전송 실패: {e}")

def get_db_data():
    if not supabase: return [], {}
    try:
        response = supabase.table('keywords').select("*").eq('is_active', True).execute()
        rows = response.data
        active_keywords = []
        ticker_map = {}
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
    ticker = ticker_map.get(keyword)
    if not ticker: return ""
    try:
        stock = yf.Ticker(ticker)
        info = stock.fast_info
        price = info.last_price
        if price is None: return ""
        
        change = price - info.previous_close
        change_pct = (change / info.previous_close) * 100
        emoji = "🔺" if change > 0 else "🦋" if change < 0 else "➖"
        
        vol_ratio = 0
        if info.last_volume and info.three_month_average_volume:
            vol_ratio = (info.last_volume / info.three_month_average_volume) * 100
        
        vol_stat = "🔥폭발" if vol_ratio >= 200 else "➖평이"
        
        result = f"\n💰 <b>{keyword} 시장 현황</b>\n{'-'*20}\n"
        result += f"현재가: {price:,.0f} ({emoji} {change_pct:.2f}%)\n"
        result += f"거래량: {vol_stat} ({vol_ratio:.0f}%)\n\n"
        return result
    except: return ""

def get_article_content(url):
    try:
        d = trafilatura.fetch_url(url)
        if d: 
            t = trafilatura.extract(d, include_comments=False)
            if t and len(t)>50: return t[:1500]
    except: pass
    try: 
        a = Article(url, language='ko')
        a.download(); a.parse()
        if len(a.text)>50: return a.text[:1500]
    except: pass
    return None

def get_gemini_summary(keyword, text_data):
    if not GEMINI_API_KEY: return "⚠️ API 키가 없습니다."
    try:
        client = genai.Client(api_key=GEMINI_API_KEY)
        
        # ★ 프롬프트를 100% 한글로 변경하고, 한국어 강제 조항을 넣었습니다.
        prompt = f"""
        당신은 유능한 펀드매니저이자 시장 분석가입니다. 
        제공된 뉴스 데이터를 바탕으로 '{keyword}' 종목에 대한 투자 브리핑을 작성하세요.

        [지시 사항]
        1. 언어: **무조건 한국어(Korean)**로 작성하십시오.
        2. 어조: 전문적이고 객관적이되, 정중한 '해요체'를 사용하십시오.
        3. 서식: 중요 숫자나 키워드는 <b>태그로 굵게 표시하십시오.

        [출력 양식]
        Part 1: ⚡ **3줄 핵심 요약** (이모지 활용, 핵심 이슈 위주)
        Part 2: 📝 **상세 시장 흐름** (300자 내외, 등락의 원인과 배경 설명)

        [뉴스 데이터]
        {text_data}
        """
        
        return client.models.generate_content(model="gemini-2.0-flash", contents=prompt).text
    except Exception as e: return f"AI Error: {e}"

def process_keyword(keyword, ticker_map):
    print(f"🚀 Analyzing: {keyword}")
    today = datetime.datetime.now().strftime("%y/%m/%d")
    stock_msg = get_stock_info(keyword, ticker_map)
    
    encoded = urllib.parse.quote(keyword)
    url = f"https://news.google.com/rss/search?q={encoded}&hl=ko&gl=KR&ceid=KR:ko"
    res = requests.get(url, timeout=5)
    soup = BeautifulSoup(res.text, "xml")
    items = soup.find_all("item")[:4]
    
    if not items: return f"💤 {keyword}: 뉴스 없음"

    llm_input = []
    news_links = []
    for i, item in enumerate(items):
        title = item.title.get_text()
        link = item.link.get_text()
        news_links.append(f"{i+1}. <a href='{link}'>{title}</a>")
        if i < 3: # 상위 3개만 내용 분석
            content = get_article_content(link)
            if content: llm_input.append(f"Title: {title}\nBody: {content}\n")

    summary = get_gemini_summary(keyword, "\n".join(llm_input))
    
    msg = f"🔥 <b>[{today}] {keyword} 브리핑</b> 🔥\n{stock_msg}{summary}\n\n<b>📰 주요 뉴스</b>\n" + "\n".join(news_links)
    send_telegram(msg)
    return f"✅ {keyword} 브리핑 완료"

# --- 앱 연동용 함수 ---
def run_batch_briefing():
    targets, ticker_map = get_db_data()
    logs = []
    if not targets: return ["⚠️ 활성화된 타겟이 없습니다."]
    
    for word in targets:
        try:
            log = process_keyword(word, ticker_map)
            logs.append(log)
        except Exception as e:
            logs.append(f"❌ {word} 에러: {e}")
        time.sleep(2)
    return logs

if __name__ == "__main__":
    run_batch_briefing()