import pandas as pd
import numpy as np
from config import Config

def calculate_rsi(series, period=14):
    """計算 RSI 指標"""
    delta = series.diff()
    up = delta.clip(lower=0)
    down = -1 * delta.clip(upper=0)
    
    # 使用指數移動平均 (EMA) 計算，alpha=1/period
    ema_up = up.ewm(com=period-1, adjust=False).mean()
    ema_down = down.ewm(com=period-1, adjust=False).mean()
    
    rs = ema_up / ema_down
    rsi = 100 - (100 / (1 + rs))
    return rsi

def calculate_macd(series, fast=12, slow=26, signal=9):
    """計算 MACD 指標"""
    exp12 = series.ewm(span=fast, adjust=False).mean()
    exp26 = series.ewm(span=slow, adjust=False).mean()
    macd_line = exp12 - exp26
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    macd_hist = macd_line - signal_line
    return macd_line, signal_line, macd_hist

def check_volume_breakout(df):
    """
    綜合技術分析：爆量 + RSI + MACD
    修正：漲跌幅改用 (今收 - 昨收) / 昨收 計算
    """
    # 取得最新一天的資料
    today = df.iloc[-1]
    
    # [新增] 取得前一天的收盤價 (昨收)
    # 如果資料只有一筆，就暫時用今天的開盤價代替，避免報錯
    prev_close = df['Close'].iloc[-2] if len(df) >= 2 else today['Open']

    # --- 1. 爆量判斷 ---
    vol_ma5 = today.get('MA5_Vol', 0)
    if vol_ma5 == 0 or pd.isna(vol_ma5):
        is_breakout = False
    else:
        is_volume_spike = today['Volume'] > (vol_ma5 * Config.VOL_MULTIPLIER)
        # 這裡通常維持 Close > Open (代表今天是紅K，買氣強)
        is_price_up = today['Close'] > today['Open']
        is_breakout = is_volume_spike and is_price_up

    # --- 2. 計算 RSI ---
    rsi_series = calculate_rsi(df['Close'])
    current_rsi = rsi_series.iloc[-1]

    # --- 3. 計算 MACD ---
    macd_line, signal_line, macd_hist = calculate_macd(df['Close'])
    current_macd = macd_line.iloc[-1]
    current_signal = signal_line.iloc[-1]
    current_hist = macd_hist.iloc[-1]
    
    # 判斷 MACD 狀態
    macd_status = "無方向"
    if current_hist > 0 and current_hist > macd_hist.iloc[-2]:
        macd_status = "多頭增強 (紅柱變長)"
    elif current_hist > 0 and current_hist < macd_hist.iloc[-2]:
        macd_status = "多頭收斂 (紅柱變短)"
    elif current_hist < 0 and current_hist < macd_hist.iloc[-2]:
        macd_status = "空頭增強 (綠柱變長)"
    elif current_hist < 0 and current_hist > macd_hist.iloc[-2]:
        macd_status = "空頭收斂 (綠柱變短)"

    # 回傳結果與詳細數據
    return is_breakout, {
        "price": round(today['Close'], 2),
        
        # [修正重點] 改用 (今收 - 昨收) / 昨收
        "change_pct": round(((today['Close'] - prev_close) / prev_close) * 100, 2),
        
        "vol_ratio": round(today['Volume'] / vol_ma5, 2) if vol_ma5 else 0,
        "is_breakout": is_breakout,
        "rsi": round(current_rsi, 1),
        "macd": round(current_macd, 2),
        "macd_signal": round(current_signal, 2),
        "macd_hist": round(current_hist, 2),
        "macd_status": macd_status
    }