import pandas as pd
import numpy as np

def calculate_rsi(series, period=14):
    """RSI (상대강도지수) 계산"""
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def calculate_macd(series, fast=12, slow=26, signal=9):
    """MACD 계산"""
    ema_fast = series.ewm(span=fast, adjust=False).mean()
    ema_slow = series.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram

def calculate_bollinger_bands(series, period=20, std_dev=2):
    """볼린저 밴드 계산"""
    sma = series.rolling(window=period).mean()
    std = series.rolling(window=period).std()
    upper_band = sma + (std * std_dev)
    lower_band = sma - (std * std_dev)
    pct_b = (series - lower_band) / (upper_band - lower_band) if (upper_band - lower_band).any() else 0.5
    return upper_band, sma, lower_band, pct_b

def calculate_stochastic(df, k_period=14, d_period=3):
    """스토캐스틱 계산"""
    low_min = df['Low'].rolling(window=k_period).min()
    high_max = df['High'].rolling(window=k_period).max()
    k_line = 100 * ((df['Close'] - low_min) / (high_max - low_min))
    d_line = k_line.rolling(window=d_period).mean()
    return k_line, d_line

def calculate_mfi(df, period=14):
    """MFI (Money Flow Index) 계산"""
    typical_price = (df['High'] + df['Low'] + df['Close']) / 3
    money_flow = typical_price * df['Volume']
    
    positive_flow = pd.Series(0.0, index=df.index)
    negative_flow = pd.Series(0.0, index=df.index)
    
    diff = typical_price.diff()
    positive_flow[diff > 0] = money_flow[diff > 0]
    negative_flow[diff < 0] = money_flow[diff < 0]
    
    pos_mf = positive_flow.rolling(window=period).sum()
    neg_mf = negative_flow.rolling(window=period).sum()
    
    mfr = pos_mf / neg_mf
    return 100 - (100 / (1 + mfr))

def calculate_atr(df, period=14):
    """ATR (평균 변동폭) 계산"""
    high_low = df['High'] - df['Low']
    high_close = np.abs(df['High'] - df['Close'].shift())
    low_close = np.abs(df['Low'] - df['Close'].shift())
    ranges = pd.concat([high_low, high_close, low_close], axis=1)
    true_range = np.max(ranges, axis=1)
    return true_range.rolling(window=period).mean()

def analyze_stock(df):
    """
    단일 종목에 대한 심층 퀀트 분석 수행 (10대 지표 통합 분석)
    """
    row_count = len(df)
    if row_count < 1:
        return {"error": "데이터가 실시간으로 존재하지 않습니다."}

    # 1. 기본 정보
    current_price = df['Close'].iloc[-1]
    
    # 2. RSI (14)
    current_rsi = None
    if row_count >= 15:
        rsi_series = calculate_rsi(df['Close'])
        current_rsi = rsi_series.iloc[-1]
    
    # 3. 거래량 비율 (20일)
    volume_ratio = None
    if row_count >= 21:
        ma20_volume = df['Volume'].rolling(window=20).mean().iloc[-1]
        current_volume = df['Volume'].iloc[-1]
        volume_ratio = (current_volume / ma20_volume) * 100 if ma20_volume > 0 else 0
    
    # 4. 52주 위치
    year_low = df['Low'].iloc[-252:].min()
    year_high = df['High'].iloc[-252:].max()
    position_52w = ((current_price - year_low) / (year_high - year_low)) * 100 if year_high > year_low else 50
    
    # 5. 이격도 (20일)
    disparity = None
    if row_count >= 20:
        ma20_price = df['Close'].rolling(window=20).mean().iloc[-1]
        disparity = (current_price / ma20_price) * 100 if ma20_price > 0 else 100
    
    # 6. MACD (12, 26, 9)
    macd_val, signal_val, hist_val = None, None, None
    if row_count >= 35:
        m_line, s_line, h_line = calculate_macd(df['Close'])
        macd_val, signal_val, hist_val = m_line.iloc[-1], s_line.iloc[-1], h_line.iloc[-1]
    
    # 7. 볼린저 밴드 (20, 2)
    upper_b, mid_b, lower_b, pct_b = None, None, None, None
    if row_count >= 20:
        upper_b, mid_b, lower_b, p_b = calculate_bollinger_bands(df['Close'])
        upper_b, mid_b, lower_b, pct_b = upper_b.iloc[-1], mid_b.iloc[-1], lower_b.iloc[-1], p_b.iloc[-1]
    
    # 8. 스토캐스틱 (14, 3, 3)
    slow_k, slow_d = None, None
    if row_count >= 20:
        k_line, d_line = calculate_stochastic(df)
        slow_k, slow_d = k_line.iloc[-1], d_line.iloc[-1]
    
    # 9. MFI (14)
    mfi_val = None
    if row_count >= 15:
        mfi_val = calculate_mfi(df).iloc[-1]
    
    # 10. 이평선 배열 (5, 20, 60, 120)
    ma_alignment = "데이터부족"
    if row_count >= 120:
        ma5 = df['Close'].rolling(window=5).mean().iloc[-1]
        ma20 = df['Close'].rolling(window=20).mean().iloc[-1]
        ma60 = df['Close'].rolling(window=60).mean().iloc[-1]
        ma120 = df['Close'].rolling(window=120).mean().iloc[-1]
        
        if ma5 > ma20 > ma60 > ma120: ma_alignment = "완전정배열"
        elif ma5 > ma20 > ma60: ma_alignment = "정배열(단선)"
        elif ma5 < ma20 < ma60 < ma120: ma_alignment = "완전역배열"
        else: ma_alignment = "혼조"
    
    # 기타: ATR 및 손절가
    current_atr, stop_loss = None, None
    if row_count >= 15:
        atr_series = calculate_atr(df)
        current_atr = atr_series.iloc[-1]
        stop_loss = current_price - (2 * current_atr)
    
    # --- 종합 점수 계산 (가중치 로직 고도화) ---
    score = 50
    if row_count >= 30:
        # RSI
        if current_rsi is not None:
            if current_rsi < 30: score += 10
            elif current_rsi > 70: score -= 10
        # 수급 (Volume Ratio)
        if volume_ratio is not None and volume_ratio > 250: score += 15
        # MACD (추세 가세)
        if hist_val is not None and hist_val > 0: score += 10
        # 볼린저 (%B)
        if pct_b is not None:
            if pct_b < 0.1: score += 10 # 하단 터치 (반등 기대)
            elif pct_b > 0.9: score -= 10 # 상단 돌파 (과열)
        # 스토캐스틱
        if slow_k is not None and slow_k < 20: score += 10
        # 이평선 배열
        if ma_alignment == "완전정배열": score += 15
        elif ma_alignment == "정배열(단선)": score += 5
        elif ma_alignment == "완전역배열": score -= 15
        # MFI
        if mfi_val is not None and mfi_val < 20: score += 10
    
    return {
        "price": current_price,
        "rsi": current_rsi,
        "volume_ratio": volume_ratio,
        "position_52w": position_52w,
        "disparity": disparity,
        "macd": {"line": macd_val, "signal": signal_val, "hist": hist_val},
        "bollinger": {"upper": upper_b, "mid": mid_b, "lower": lower_b, "pct_b": pct_b},
        "stochastic": {"k": slow_k, "d": slow_d},
        "mfi": mfi_val,
        "ma_alignment": ma_alignment,
        "atr": current_atr,
        "stop_loss": stop_loss,
        "score": min(max(score, 0), 100),
        "data_points": row_count
    }
