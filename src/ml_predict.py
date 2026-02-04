import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestClassifier
#from sklearn.model_selection import GridSearchCV # [新增] 自動調參工具
from src.strategy import calculate_rsi, calculate_macd

def prepare_features(df):
    """
    特徵工程升級版：加入歷史數據 (Lag Features)
    """
    df = df.copy()
    
    # --- 1. 基礎技術指標 ---
    df['RSI'] = calculate_rsi(df['Close'])
    macd, signal, hist = calculate_macd(df['Close'])
    df['MACD_Hist'] = hist
    
    df['MA20'] = df['Close'].rolling(window=20).mean()
    df['Bias_20'] = (df['Close'] - df['MA20']) / df['MA20'].replace(0, np.nan)
    df['Vol_Change'] = df['Volume'].pct_change()
    
    # --- 2. [新增] 歷史特徵 (Lag Features) ---
    # 讓 AI 知道「昨天」和「前天」發生什麼事
    # Lag 1 = 昨天, Lag 2 = 前天
    
    # 昨天的漲跌幅
    df['Return'] = df['Close'].pct_change()
    df['Return_Lag1'] = df['Return'].shift(1)
    df['Return_Lag2'] = df['Return'].shift(2)
    
    # 昨天的成交量變化
    df['Vol_Change_Lag1'] = df['Vol_Change'].shift(1)
    
    # 昨天的 RSI
    df['RSI_Lag1'] = df['RSI'].shift(1)
    
    # --- 3. 預測目標 ---
    df['Target'] = (df['Close'].shift(-1) > df['Close']).astype(int)
    
    # --- 4. 清洗資料 ---
    df.replace([np.inf, -np.inf], np.nan, inplace=True)
    df = df.dropna()
    
    return df

def predict_next_day(df):
    """
    ☁️ 雲端輕量版預測：專為 Render 免費版優化
    移除 GridSearchCV 與多執行緒，確保不會因記憶體不足而當機。
    """
    # 1. 資料長度檢查
    if len(df) < 100:
        return None

    try:
        # 假設你有定義 prepare_features 函式
        data = prepare_features(df)
        
        # 準備好資料後，再次檢查長度 (因為 Lag 特徵會產生 NaN 被刪除)
        if len(data) < 60:
            return None
        
        # 2. 定義特徵欄位 (保留你原本的設計)
        feature_cols = [
            'RSI', 'MACD_Hist', 'Bias_20', 'Vol_Change',
            'Return_Lag1', 'Return_Lag2', # 昨天的漲幅、前天的漲幅
            'Vol_Change_Lag1', 'RSI_Lag1' # 昨天的量、昨天的RSI
        ]
        
        # 檢查是否所有欄位都存在
        missing_cols = [col for col in feature_cols if col not in data.columns]
        if missing_cols:
            print(f"⚠️ 缺少特徵欄位: {missing_cols}")
            return None

        X = data[feature_cols]
        y = data['Target']
        
        # 3. 切分訓練集與預測集
        X_train = X.iloc[:-1]
        y_train = y.iloc[:-1]
        X_new = X.iloc[[-1]] 
        
        # ======================================================
        # 🔥【關鍵修改】雲端生存模式
        # ======================================================
        
        # 不再使用 GridSearch 亂槍打鳥，直接指定一組穩定的參數
        model = RandomForestClassifier(
            n_estimators=30,     # 樹種 30 棵就好 (原本可能預設 100)
            max_depth=5,         # 樹高限制 5 層 (避免過度擬合 + 省記憶體)
            min_samples_split=5, # 稍微保守一點的分裂
            n_jobs=1,            # 【救命關鍵】強制單核心！絕對不能用 -1
            random_state=42
        )
        
        # 直接訓練一次 (原本要訓練 54 次)
        model.fit(X_train, y_train)
        
        # --- (選用) 還是可以印出特徵重要性，讓你跟教授有東西講 ---
        # print("📊 [AI 權重] " + ", ".join([f"{feature_cols[i]}:{model.feature_importances_[i]:.2f}" for i in np.argsort(model.feature_importances_)[::-1][:3]]))
        
        # 4. 預測
        probs = model.predict_proba(X_new)[0]
        up_prob = round(probs[1] * 100, 1) 
        
        return up_prob
        
    except Exception as e:
        print(f"❌ ML 預測失敗 (記憶體保護模式): {e}")
        # 回傳 None 讓外層去處理 (例如顯示「資料不足」)
        return None