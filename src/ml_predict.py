import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import GridSearchCV # [新增] 自動調參工具
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
    升級版預測：使用 GridSearchCV 尋找最佳參數
    """
    # 因為加了 Lag Features，前面會多出幾天 NaN，所以資料長度要求要更高
    if len(df) < 100:
        return None

    try:
        data = prepare_features(df)
        
        if len(data) < 60:
            return None
        
        # 定義特徵欄位 (加入新的 Lag 特徵)
        feature_cols = [
            'RSI', 'MACD_Hist', 'Bias_20', 'Vol_Change',
            'Return_Lag1', 'Return_Lag2', # 昨天的漲幅、前天的漲幅
            'Vol_Change_Lag1', 'RSI_Lag1' # 昨天的量、昨天的RSI
        ]
        
        X = data[feature_cols]
        y = data['Target']
        
        # 切分訓練集與預測集
        X_train = X.iloc[:-1]
        y_train = y.iloc[:-1]
        X_new = X.iloc[[-1]] 
        
        # --- [新增] 自動參數調整 (Grid Search) ---
        # 告訴電腦試試看這些組合，找出這支股票最適合的參數
        param_grid = {
            'n_estimators': [50, 100, 200],      # 樹的數量
            'max_depth': [3, 5, 10],             # 樹的深度 (太深會死背，太淺學不會)
            'min_samples_split': [2, 5]          # 節點分割最小樣本數
        }
        
        rf = RandomForestClassifier(random_state=42)
        
        # cv=3 代表做 3 次交叉驗證 (Cross Validation)
        grid_search = GridSearchCV(estimator=rf, param_grid=param_grid, cv=3, n_jobs=-1)
        
        # 開始訓練 (這一步會比較久一點，因為它在狂試參數)
        grid_search.fit(X_train, y_train)
        
        # 取得最強模型
        best_model = grid_search.best_estimator_
        
        # --- 印出特徵重要性 (用最強模型看) ---
        print(f"\n🧠 [AI 最佳參數] {grid_search.best_params_}")
        print("📊 [AI 最看重指標]")
        importances = best_model.feature_importances_
        indices = np.argsort(importances)[::-1]
        
        for i in indices:
            print(f"   🔹 {feature_cols[i]}: {importances[i]:.4f}")
        print("-" * 30)
        
        # 預測
        probs = best_model.predict_proba(X_new)[0]
        up_prob = round(probs[1] * 100, 1) 
        
        return up_prob
        
    except Exception as e:
        print(f"❌ ML 預測失敗: {e}")
        return None