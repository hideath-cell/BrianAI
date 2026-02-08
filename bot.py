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
import random

# 1. 환경변수 로드
load_dotenv()
TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
GEMINI_API_KEY = os.environ.get("GOOGLE_API_KEY")
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

# 2. Supabase 연결
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY) if SUPABASE_URL and SUPABASE_KEY else None

# --- [유틸리티] 텔레그램 전송 ---
def send_telegram(text):
    if not TOKEN or not CHAT_ID: return
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    data = {"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML", "disable_web_page_preview": "true"}
    try: requests.post(url, data=data, timeout=5)
    except Exception as e: print(f"전송 실패: {e}")

# --- [유틸리티] DB 조회 ---
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

from quant_analyzer import analyze_stock

# --- [유틸리티] 지표 아이콘 판별 ---
def get_brief_icon(name, val):
    if val is None: return "⚪"
    if name == "score":
        if val >= 70: return "💎"
        if val <= 30: return "⚠️"
        return "📈" if val >= 50 else "📉"
    return ""

# --- [유틸리티] 주가 정보 및 퀀트 분석 조회 ---
def get_stock_info(keyword, ticker_map):
    ticker = ticker_map.get(keyword)
    if not ticker: return ""
    try:
        # 1년치 데이터 가져오기 (퀀트 엔진용)
        stock = yf.Ticker(ticker)
        df = stock.history(period="1y")
        if df.empty: return ""
        
        # 퀀트 분석 수행
        m = analyze_stock(df)
        if "error" in m: return f"\n⚠️ {keyword}: 데이터 부족으로 분석 불가\n"

        price = m['price']
        # 전일 종가 기반 등락 계산 (yf match)
        prev_price = df['Close'].iloc[-2] if len(df) >= 2 else price
        change_pct = ((price - prev_price) / prev_price) * 100
        emoji = "🔺" if change_pct > 0 else "🦋" if change_pct < 0 else "➖"
        
        # 퀀트 스코어 및 주요 지표 요약
        score_icon = get_brief_icon("score", m['score'])
        
        result = f"\n📊 <b>{keyword} 퀀트 브리핑</b>\n{'-'*20}\n"
        result += f"현재가: {price:,.0f} ({emoji} {change_pct:.2f}%)\n"
        result += f"종합점수: {score_icon} <b>{m['score']}점</b>\n"
        
        # 주요 지표 1줄 요약
        rsi_val = f"{m['rsi']:.0f}" if m['rsi'] else "-"
        vol_val = f"{m['volume_ratio']:.0f}%" if m['volume_ratio'] else "-"
        result += f"RSI: {rsi_val} | 수급: {vol_val} | 52주: {m['position_52w']:.0f}%\n"
        
        if m['stop_loss']:
            result += f"추천손절: 🛡️ {m['stop_loss']:,.0f}원\n"
        
        return result + "\n"
    except Exception as e:
        print(f"Stock Info Error ({keyword}): {e}")
        return ""

# --- [핵심] 뉴스 수집 엔진 (구글 + 빙) ---
def fetch_rss_items(keyword):
    """구글 뉴스를 먼저 털고, 없으면 빙 뉴스를 텁니다."""
    encoded = urllib.parse.quote(keyword)
    items = []
    
    # 1. 검색 엔진 리스트 (우선순위: 구글 -> 빙)
    search_urls = [
        ("Google", f"https://news.google.com/rss/search?q={encoded}&hl=ko&gl=KR&ceid=KR:ko"),
        ("Bing", f"https://www.bing.com/news/search?q={encoded}&format=rss")
    ]
    
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}

    for source_name, url in search_urls:
        if len(items) >= 4: break # 이미 충분하면 중단
        try:
            print(f"📡 {source_name} 검색 시도...")
            res = requests.get(url, headers=headers, timeout=5)
            soup = BeautifulSoup(res.text, "xml")
            found_items = soup.find_all("item")
            
            for item in found_items:
                title = item.title.get_text()
                link = item.link.get_text()
                # RSS에 있는 요약본(description) 추출
                snippet = ""
                if item.description:
                    snippet = BeautifulSoup(item.description.get_text(), "html.parser").get_text()
                
                items.append({"source": source_name, "title": title, "link": link, "snippet": snippet})
                if len(items) >= 4: break
        except Exception as e:
            print(f"⚠️ {source_name} 검색 실패: {e}")
            
    return items

# --- [핵심] 본문 추출 엔진 (Trafilatura + Newspaper3k) ---
def get_article_content(url):
    """여러 라이브러리를 동원해 본문 추출 시도"""
    # 1. Trafilatura 시도 (가장 깔끔함)
    try:
        d = trafilatura.fetch_url(url)
        if d:
            t = trafilatura.extract(d, include_comments=False, include_tables=False)
            if t and len(t) > 50: return t[:1500]
    except: pass
    
    # 2. Newspaper3k 시도 (전통의 강자)
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        a = Article(url, language='ko', browser_user_agent=headers['User-Agent'])
        a.download()
        a.parse()
        if len(a.text) > 50: return a.text[:1500]
    except: pass

    return None # 다 실패하면 None 반환

# --- [핵심] AI 요약 (한글 강제) ---
def get_gemini_summary(keyword, text_data):
    if not GEMINI_API_KEY: return "⚠️ API 키가 없습니다."
    
    try:
        client = genai.Client(api_key=GEMINI_API_KEY)
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

# --- 메인 로직 ---
def process_keyword(keyword, ticker_map):
    print(f"🚀 Analyzing: {keyword}")
    today = datetime.datetime.now().strftime("%y/%m/%d")
    stock_msg = get_stock_info(keyword, ticker_map)
    
    # 1. 뉴스 수집 (구글 -> 빙)
    news_items = fetch_rss_items(keyword)
    
    if not news_items: 
        return f"💤 {keyword}: 뉴스 없음 (Google & Bing 모두 실패)"

    llm_input = []
    news_links = []
    
    # 2. 본문 추출 및 데이터 조립
    for i, item in enumerate(news_items):
        title = item['title']
        link = item['link']
        snippet = item['snippet']
        source = item['source']
        
        news_links.append(f"{i+1}. [{source}] <a href='{link}'>{title}</a>")
        
        # 본문 추출 시도
        content = get_article_content(link)
        
        if content:
            # 본문 성공 시
            llm_input.append(f"[기사 {i+1}] 제목: {title}\n내용: {content}\n")
        else:
            # 본문 실패 시 -> RSS Snippet(요약) 사용
            llm_input.append(f"[기사 {i+1}] 제목: {title}\n요약(접속불가): {snippet}\n")

    # 3. AI 분석
    # 데이터가 너무 적으면 경고하지만, snippet이라도 있으면 진행
    full_text = "\n".join(llm_input)
    if len(full_text) < 30:
        return f"⚠️ {keyword}: 분석할 데이터 부족"

    summary = get_gemini_summary(keyword, full_text)
    
    msg = f"🔥 <b>[{today}] {keyword} 브리핑</b> 🔥\n{stock_msg}{summary}\n\n<b>📰 주요 뉴스</b>\n" + "\n".join(news_links)
    send_telegram(msg)
    return f"✅ {keyword} 브리핑 완료"

# --- 앱 연동용 ---
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