import os
import sys

# Streamlit 경고 메시지 강제 억제 (최우선 순위)
os.environ["STREAMLIT_SERVER_GATHER_USAGE_STATS"] = "false"
import logging
logging.getLogger("streamlit.runtime.scriptrunner_utils.script_run_context").setLevel(logging.ERROR)
logging.getLogger("streamlit").setLevel(logging.ERROR)

import pandas as pd
import time
import random

from utils import init_connection, fetch_stock_data, fix_encoding
from quant_analyzer import analyze_stock

def print_separator():
    print("-" * 70)

def evaluate_stock(row):
    """
    개별 종목에 대한 10대 지표 분석 및 리포트 출력
    """
    keyword = row['keyword']
    ticker = row['ticker']
    
    print(f"\n[종목 분석: {keyword} ({ticker or '티커없음'})]")
    
    if not ticker:
        print("  ! 분석 불가: 티커 정보가 없습니다.")
        return

    # 1. 1년치 데이터 가져오기 (고급 지표용)
    data = fetch_stock_data(ticker, period="1y")
    if not data or data['history'] is None:
        print("  ! 분석 불가: 주가 데이터를 가져올 수 없습니다.")
        return
    
    # 2. 퀀트 분석 엔진 가동 (10대 지표)
    metrics = analyze_stock(data['history'])
    
    if "error" in metrics:
        print(f"  ! {metrics['error']}")
        return

    # 3. 결과 출력 (그룹화하여 가독성 증대)
    print_separator()
    print(f"데이터 포인트: {metrics['data_points']}일 확보됨 " + ("(일부 지표 제한)" if metrics['data_points'] < 120 else "(충분)"))
    print_separator()
    print(f"{'지표 분류 / 명칭':<25} | {'현재값':<15} | {'상태 및 평가'}")
    print_separator()
    
    # --- 모멘텀 및 강도 (Momentum) ---
    # RSI
    rsi = metrics['rsi']
    rsi_eval = f"{rsi:>13.1f}" if rsi is not None else "데이터부족"
    rsi_desc = "과매수 주의" if rsi and rsi > 70 else "과매도 기회" if rsi and rsi < 30 else "중립"
    print(f"{'[모멘텀] RSI (14)':<25} | {rsi_eval:<15} | {rsi_desc}")
    
    # MFI
    mfi = metrics['mfi']
    mfi_eval = f"{mfi:>13.1f}" if mfi is not None else "데이터부족"
    mfi_desc = "자금유입강함" if mfi and mfi > 80 else "자금이탈주의" if mfi and mfi < 20 else "보통"
    print(f"{'[모멘텀] MFI (14)':<25} | {mfi_eval:<15} | {mfi_desc}")
    
    # 스토캐스틱
    stoch = metrics['stochastic']
    stoch_eval = f"K:{stoch['k']:.1f}, D:{stoch['d']:.1f}" if stoch['k'] is not None else "데이터부족"
    stoch_desc = "단기침체(반등권)" if stoch['k'] and stoch['k'] < 20 else "단기과열" if stoch['k'] and stoch['k'] > 80 else "중립"
    print(f"{'[모멘텀] Stochastic':<25} | {stoch_eval:<15} | {stoch_desc}")

    # --- 추세 분석 (Trend) ---
    # MACD
    macd = metrics['macd']
    macd_eval = f"H:{macd['hist']:.1f}" if macd['hist'] is not None else "데이터부족"
    macd_desc = "상승추세강화" if macd['hist'] and macd['hist'] > 0 else "하락추세지속" if macd['hist'] and macd['hist'] < 0 else "-"
    print(f"{'[추세] MACD Hist':<25} | {macd_eval:<15} | {macd_desc}")
    
    # 이평선 배열
    ma_align = metrics['ma_alignment']
    print(f"{'[추세] MA Alignment':<25} | {ma_align:<15} | {'추세 유지력 평가'}")
    
    # 이격도
    disp = metrics['disparity']
    disp_eval = f"{disp:>13.1f}%" if disp is not None else "데이터부족"
    disp_desc = "이격과다(조심)" if disp and disp > 110 else "바닥권이탈" if disp and disp < 95 else "적정"
    print(f"{'[추세] 이격도 (20일)':<25} | {disp_eval:<15} | {disp_desc}")

    # --- 변동성 및 가격 위치 (Volatility / Position) ---
    # 볼린저 밴드
    bb = metrics['bollinger']
    bb_eval = f"%B:{bb['pct_b']:.2f}" if bb['pct_b'] is not None else "데이터부족"
    bb_desc = "밴드하단(매수검토)" if bb['pct_b'] is not None and bb['pct_b'] < 0.1 else "밴드상단돌파" if bb['pct_b'] is not None and bb['pct_b'] > 0.9 else "밴드내수렴"
    print(f"{'[변동성] Bollinger %B':<25} | {bb_eval:<15} | {bb_desc}")
    
    # 거래량 비율
    vol = metrics['volume_ratio']
    vol_eval = f"{vol:>13.1f}%" if vol is not None else "데이터부족"
    vol_desc = "수급폭발!" if vol and vol > 250 else "거래침체" if vol and vol < 50 else "보통"
    print(f"{'[변동성] 거래량 비율':<25} | {vol_eval:<15} | {vol_desc}")
    
    # 52주 위치
    pos = metrics['position_52w']
    pos_desc = "신고가인근" if pos > 90 else "역사적바닥" if pos < 10 else "중간지점"
    print(f"{'[위치] 52주 가격위치':<25} | {pos:>13.1f}% | {pos_desc}")

    # --- 리스크 관리 (Risk Management) ---
    print_separator()
    if metrics['atr'] is not None:
        print(f"[*] ATR(변동폭): {metrics['atr']:.0f}원 | 추천 손절가(2-ATR): {metrics['stop_loss']:,.0f}원")
    else:
        print("[*] 리스크 관리: 데이터 부족으로 손절가 계산 불가")
    
    print(f"[*] 종합 퀀트 스코어: {metrics['score']} / 100")
    print_separator()

def main():
    fix_encoding()
    print("\n" + "="*70)
    print("📈 심층 퀀트 분석 리포터 v1.0")
    print("="*70)
    
    supabase = init_connection()
    if not supabase:
        print("❌ DB 연결 실패")
        return

    # DB에서 활성 종목 가져오기
    res = supabase.table('keywords').select("*").eq('is_active', True).execute()
    stocks = res.data
    
    if not stocks:
        print("🤔 분석할 활성 종목이 없습니다.")
        return

    print(f"📡 총 {len(stocks)}개의 종목을 순차적으로 분석합니다 (안전 지연 시간 포함)...\n")
    
    for idx, stock in enumerate(stocks):
        evaluate_stock(stock)
        
        # 마지막 종목이 아니면 랜덤 지연 추가 (1.0~2.5초)
        if idx < len(stocks) - 1:
            delay = random.uniform(1.0, 2.5)
            print(f"  [Wait] 안전을 위해 {delay:.1f}초 대기 중...")
            time.sleep(delay)
            print_separator()

if __name__ == "__main__":
    main()
