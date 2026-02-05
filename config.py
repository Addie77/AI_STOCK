# config.py

import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    # Flask 必要的加密金鑰
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'your-very-secret-key'
    
    GOOGLE_API_KEY = os.getenv('GOOGLE_API_KEY')
    
    # LINE 設定
    LINE_CHANNEL_ACCESS_TOKEN = os.getenv('LINE_CHANNEL_ACCESS_TOKEN')
    LINE_CHANNEL_SECRET = os.getenv('LINE_CHANNEL_SECRET')
    
    # [資料庫設定] (如果你之後有要用資料庫)
    SQLALCHEMY_DATABASE_URI = 'sqlite:///stocks.db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # [模型設定] 這裡控制你要用哪個 Gemini 版本
    GEMINI_MODEL_NAME = "gemini-2.5-flash"
    #GEMINI_MODEL_NAME = "gemini-2.5-flash-lite"  # 較小的模型，速度更快但可能效果稍差
    #GEMINI_MODEL_NAME = "gemini-3-flash-preview"  # 最新的 Gemini 3 模型，效果最好但速度較慢 
    
    # [策略設定] 這裡定義什麼叫「爆量」
    # 1.5 代表成交量是過去 5 日均量的 1.5 倍
    VOL_MULTIPLIER = 1.5
    
    # [新增] 回測策略參數
    BACKTEST_VOL_MULTIPLIER = 1.25  # 量能倍數
    BACKTEST_RSI_LIMIT = 82         # RSI 上限
    STOP_LOSS_PCT = 0.05            # 停損 (5%)
    TAKE_PROFIT_PCT = 0.10          # 停利 (10%)


