import pandas as pd
import numpy as np
from config import Config
from src.strategy import calculate_rsi

def run_backtest(df):
    """
    回測策略 (最終殺手鐧 - 雙斜率過濾)：
    1. 【雙斜率共振】 月線(MA20) 與 季線(MA60) 都必須「趨勢向上(斜率>0)」才准買。
       這能完美過濾掉「空頭走勢中的反彈假突破」。
    2. 其他條件維持：爆量、收紅、RSI保護、停損停利。
    """
    df = df.copy()
    
    trades = [] 
    holding_days = 5 
    
    # --- 策略參數 ---
    stop_loss_pct = Config.STOP_LOSS_PCT
    take_profit_pct = Config.TAKE_PROFIT_PCT
    
    backtest_vol_multiplier = Config.BACKTEST_VOL_MULTIPLIER
    rsi_limit = Config.BACKTEST_RSI_LIMIT
    
    # --- 1. 準備指標 ---
    if 'MA5_Vol' not in df.columns:
        df['MA5_Vol'] = df['Volume'].rolling(window=5).mean()
        
    df['MA20'] = df['Close'].rolling(window=20).mean()
    df['MA60'] = df['Close'].rolling(window=60).mean()
    df['RSI'] = calculate_rsi(df['Close'])
    
    # 計算斜率
    df['MA20_Slope'] = df['MA20'].diff()
    df['MA60_Slope'] = df['MA60'].diff() # [新增] 季線斜率

    start_idx = max(60, len(df) - 250)
    
    i = start_idx
    while i < len(df) - holding_days:
        
        today = df.iloc[i]
        vol_ma5 = today['MA5_Vol']
        rsi = today['RSI']
        ma20_slope = today['MA20_Slope']
        ma60_slope = today['MA60_Slope']
        
        # 防呆
        if vol_ma5 == 0 or pd.isna(rsi) or pd.isna(ma20_slope) or pd.isna(ma60_slope):
            i += 1
            continue

        # --- 2. 進場條件 ---
        
        # A: 雙均線 + 雙斜率 (最強濾網)
        # 只有當「中長期趨勢」都同步向上時，才視為安全進場點
        condition_trend = (today['Close'] > today['MA20']) and \
                          (ma20_slope > 0) and \
                          (today['Close'] > today['MA60']) and \
                          (ma60_slope > 0) 
        
        # B: 量能與型態
        condition_vol = today['Volume'] > (vol_ma5 * backtest_vol_multiplier)
        condition_red = today['Close'] > today['Open']
        condition_rsi = rsi < rsi_limit
        
        # 綜合判斷
        if condition_trend and condition_vol and condition_red and condition_rsi:
            
            buy_price = today['Close']
            buy_date = df.index[i]
            
            # --- 3. 模擬持有 ---
            sell_price = 0
            sell_date = None
            return_pct = 0
            note = "持有到期"
            
            is_closed = False 
            
            for j in range(1, holding_days + 1):
                future_day = df.iloc[i + j]
                
                # 停損
                if future_day['Low'] <= (buy_price * (1 - stop_loss_pct)):
                    sell_price = buy_price * (1 - stop_loss_pct)
                    sell_date = df.index[i + j]
                    return_pct = -stop_loss_pct
                    note = "停損出場"
                    is_closed = True
                    break
                
                # 停利
                if future_day['High'] >= (buy_price * (1 + take_profit_pct)):
                    sell_price = buy_price * (1 + take_profit_pct)
                    sell_date = df.index[i + j]
                    return_pct = take_profit_pct
                    note = "停利出場 🎉"
                    is_closed = True
                    break
            
            if not is_closed:
                sell_day = df.iloc[i + holding_days]
                sell_price = sell_day['Close']
                sell_date = df.index[i + holding_days]
                return_pct = (sell_price - buy_price) / buy_price
            
            trades.append({
                "buy_date": buy_date,
                "buy_price": buy_price,
                "sell_date": sell_date,
                "sell_price": sell_price,
                "return": return_pct,
                "note": note
            })
            
            i += holding_days
        else:
            i += 1

    # --- 4. 統計結果 ---
    total_trades = len(trades)
    if total_trades == 0:
        return {
            "total_trades": 0,
            "win_rate": 0,
            "total_return": 0,
            "strategy_name": "雙均線雙斜率共振"
        }

    win_count = sum(1 for t in trades if t['return'] > 0)
    win_rate = round((win_count / total_trades) * 100, 1)
    
    total_return = 1.0
    for t in trades:
        total_return *= (1 + t['return'])
    
    total_return_pct = round((total_return - 1) * 100, 1)

    return {
        "total_trades": total_trades,
        "win_rate": win_rate,
        "total_return": total_return_pct,
        "strategy_name": "雙均線雙斜率共振"
    }