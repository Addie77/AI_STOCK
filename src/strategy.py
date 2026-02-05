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
        # 如果 df 裡還沒算 MA5_Vol，這裡補算一下
        vol_ma5 = df['Volume'].iloc[-6:-1].mean() if len(df) >= 6 else today['Volume']
        
    if vol_ma5 == 0:
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
    if len(macd_hist) >= 2:
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

def check_buy_signal(df):
    """
    🚀 實戰訊號檢查 (新增功能)
    判斷「今天」是否符合回測中的「雙均線雙斜率共振」策略
    回傳: (是否買進: bool, 原因描述: str)
    """
    # 1. 確保資料夠多 (計算 MA60 至少要 60 筆)
    if len(df) < 60:
        return False, "⚠️ 資料不足 (新上市?)"

    # 為了避免影響原始 df，使用 copy
    temp_df = df.copy()

    # 2. 確保必要指標已計算 (MA20, MA60, RSI)
    temp_df['MA20'] = temp_df['Close'].rolling(window=20).mean()
    temp_df['MA60'] = temp_df['Close'].rolling(window=60).mean()
    temp_df['RSI'] = calculate_rsi(temp_df['Close'])
    
    # 取得今天的數據 (最後一列)
    today = temp_df.iloc[-1]
    # 取得昨天的數據 (倒數第二列，用來算斜率)
    yesterday = temp_df.iloc[-2]

    # 計算斜率 (今天 - 昨天)
    ma20_slope = today['MA20'] - yesterday['MA20']
    ma60_slope = today['MA60'] - yesterday['MA60']
    
    # 準備比較用的 5日均量 (不含今天，前5天的平均)
    vol_ma5 = temp_df['Volume'].iloc[-6:-1].mean()
    
    # --- 3. 讀取 Config 參數 ---
    # 如果 Config 裡沒有設定 BACKTEST_ 開頭的參數，就用預設值
    vol_multiplier = getattr(Config, 'BACKTEST_VOL_MULTIPLIER', 2.0)
    rsi_limit = getattr(Config, 'BACKTEST_RSI_LIMIT', 75)

    # --- 4. 逐一檢查條件 (跟回測邏輯一模一樣) ---

    # A. 趨勢條件 (雙均線 + 雙斜率)
    # 確保收盤在均線之上，且均線正在往上翹
    trend_ok = (today['Close'] > today['MA20']) and \
               (ma20_slope > 0) and \
               (today['Close'] > today['MA60']) and \
               (ma60_slope > 0)

    # B. 動能條件 (爆量)
    vol_ok = today['Volume'] > (vol_ma5 * vol_multiplier)

    # C. 型態條件 (收紅K)
    candle_ok = today['Close'] > today['Open']

    # D. 風險條件 (RSI)
    rsi_ok = today['RSI'] < rsi_limit

    # --- 5. 產生結論 ---
    reasons = []
    
    if trend_ok: reasons.append("✅趨勢多頭")
    else: reasons.append("❌趨勢未確認")
    
    if vol_ok: reasons.append("✅量能爆發")
    else: reasons.append("❌量能平平")
    
    if candle_ok: reasons.append("✅收紅")
    else: reasons.append("❌收黑/平")
    
    if rsi_ok: reasons.append("✅RSI安全")
    else: reasons.append("❌RSI過熱")

    # 綜合判斷 (全部 True 才是 True)
    is_buy = trend_ok and vol_ok and candle_ok and rsi_ok
    
    # 組合回傳訊息
    msg = " | ".join(reasons)
    
    return is_buy, msg