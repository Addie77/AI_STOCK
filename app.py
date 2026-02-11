from flask import Flask, render_template, request, redirect, url_for, abort
from flask_sqlalchemy import SQLAlchemy
from GoogleNews import GoogleNews
import google.generativeai as genai
from pytz import timezone
import os
import datetime
from flask_caching import Cache

# --- 引入 LINE Bot 相關套件 ---
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage

# --- 引入排程套件 ---
from apscheduler.schedulers.background import BackgroundScheduler
import atexit

# 引入你的功能模組
from src import market_data, strategy, chart, chips, ml_predict, backtest, sentiment
from config import Config 

app = Flask(__name__)
app.config.from_object(Config)

# ===========================
# 🔥 快取設定 (關鍵保護機制)
# ===========================
# 設定快取存活時間為 300 秒 (5分鐘)
cache = Cache(app, config={'CACHE_TYPE': 'SimpleCache'})

# 初始化資料庫
db = SQLAlchemy(app)

# 初始化 Gemini
genai.configure(api_key=app.config.get('GOOGLE_API_KEY'))

# 初始化 LINE Bot
line_bot_api = LineBotApi(app.config.get('LINE_CHANNEL_ACCESS_TOKEN'))
handler = WebhookHandler(app.config.get('LINE_CHANNEL_SECRET'))

# --- 資料庫模型 ---
class Watchlist(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    ticker = db.Column(db.String(10), unique=True, nullable=False)

with app.app_context():
    db.create_all()

# ===========================
# 🛡️ 快取保護層 (新增函式)
# ===========================
@cache.memoize(timeout=300)
def get_cached_data(ticker):
    """
    這是一個有「快取保護」的抓資料函式。
    5分鐘內重複查詢同一支股票，會直接回傳舊資料，
    完全不消耗 Yahoo 流量，避免被鎖 IP！
    """
    print(f"📥 [Cache] 正在處理 {ticker} (若5分鐘內查過則不下載)...")
    return market_data.get_stock_data(ticker)

# ===========================
#  PART 1: 定時推播任務
# ===========================

def send_morning_report():
    """ 每天早上執行的任務：掃描自選股並推播 """
    user_id = os.getenv('ADMIN_USER_ID')
    if not user_id:
        print("❌ 尚未設定 ADMIN_USER_ID，無法推播")
        return

    print("⏰ 開始執行每日早報推播...")
    
    with app.app_context():
        watchlist = Watchlist.query.all()
        if not watchlist:
            # 省略空清單處理...
            return

        report_content = "🌞 早安！您的自選股快報：\n"
        
        for stock in watchlist:
            try:
                ticker = stock.ticker
                
                # 🔥 改用快取函式抓資料
                df, valid_ticker = get_cached_data(ticker)
                
                if df is not None:
                    today = df.iloc[-1]
                    price = round(today['Close'], 2)
                    prev_close = df['Close'].iloc[-2] if len(df) >= 2 else price
                    change_pct = round(((price - prev_close) / prev_close) * 100, 2)
                    
                    emoji = "🔴" if change_pct > 0 else "🟢" if change_pct < 0 else "⚪"
                    report_content += f"{emoji} {valid_ticker.replace('.TW','')}: {price} ({change_pct}%)\n"
            except Exception as e:
                print(f"分析 {stock.ticker} 失敗: {e}")

        report_content += "\n💡 輸入股票代號可查看詳細 AI 與策略分析！"

        try:
            line_bot_api.push_message(user_id, TextSendMessage(text=report_content))
            print("✅ 早報推播成功！")
        except Exception as e:
            print(f"❌ 推播失敗: {e}")

# 啟動排程器
if not app.debug or os.environ.get('WERKZEUG_RUN_MAIN') == 'true':
    tw_timezone = timezone('Asia/Taipei') 
    scheduler = BackgroundScheduler(timezone=tw_timezone)
    scheduler.add_job(func=send_morning_report, trigger="cron", hour=9, minute=0)
    scheduler.start()
    atexit.register(lambda: scheduler.shutdown())

# ===========================
#  PART 2: LINE Bot 互動
# ===========================

@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return 'OK'

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_msg = event.message.text.strip()
    
    if user_msg.upper() == "ID":
        user_id = event.source.user_id
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"您的 User ID 是：\n{user_id}\n(請貼到 .env 檔案中)"))
        return

    if user_msg.isdigit() or user_msg.upper().endswith('.TW'):
        ticker = user_msg if user_msg.upper().endswith('.TW') else f"{user_msg}.TW"
        
        try:
            # 🔥 改用快取函式抓資料 (這裡最容易因為使用者連點而被鎖)
            df, valid_ticker = get_cached_data(ticker)
            
            if df is None:
                line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"❌ 找不到 {ticker}"))
                return

            # 2. 執行策略分析
            is_breakout, tech_info = strategy.check_volume_breakout(df)
            is_buy, signal_msg = strategy.check_buy_signal(df)
            
            price = tech_info['price']
            change = tech_info['change_pct']
            vol_ratio = tech_info['vol_ratio']
            stock_name = valid_ticker.replace('.TWO', '').replace('.TW', '')
            
            # 3. 抓新聞 & AI 分析
            # 新聞也建議稍微快取，但目前先只做股價
            news = market_data.get_recent_news(stock_name)
            
            model_name = app.config.get('GEMINI_MODEL_NAME')
            model = genai.GenerativeModel(model_name)
            
            news_text = "\n".join([f"- {n}" for n in news]) if news else "無重大新聞"
            
            prompt = f"""
            你是一位台股分析師。請用繁體中文針對「{stock_name}」給出 50 字以內的簡評。
            數據：現價 {price} (漲幅 {change}%)，爆量 {vol_ratio} 倍。
            策略訊號：{'建議買進' if is_buy else '觀望'} ({signal_msg})。
            新聞：{news_text}
            """
            
            response = model.generate_content(prompt)
            ai_comment = response.text.strip()

            signal_icon = "🚀 強力買進" if is_buy else "⏸️ 觀望"
            
            result_msg = (
                f"📊 【{stock_name}】\n"
                f"💰 {price} ({change}%)\n"
                f"📈 {'🔥 爆量' if is_breakout else '🐢 盤整'}\n"
                f"----------------\n"
                f"🎯 雙均線策略:\n"
                f"【{signal_icon}】\n"
                f"{signal_msg}\n"
                f"----------------\n"
                f"🤖 AI：{ai_comment}\n"
                f"----------------\n"
                f"💡 詳情請見網頁版"
            )
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=result_msg))

        except Exception as e:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"系統忙碌中: {str(e)}"))
    else:
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="請輸入股票代號 (如 2330)"))

# ===========================
#  PART 3: 網頁路由
# ===========================

@app.route('/add/<ticker>')
def add_to_watchlist(ticker):
    exists = Watchlist.query.filter_by(ticker=ticker).first()
    if not exists:
        new_stock = Watchlist(ticker=ticker)
        db.session.add(new_stock)
        db.session.commit()
    return redirect(url_for('index'))

@app.route('/delete/<int:id>')
def delete_from_watchlist(id):
    stock = Watchlist.query.get_or_404(id)
    db.session.delete(stock)
    db.session.commit()
    return redirect(url_for('index'))

@app.route('/', methods=['GET', 'POST'])
def index():
    watchlist = Watchlist.query.all()
    if request.method == 'POST':
        ticker = request.form.get('ticker').strip()
        if not ticker.endswith('.TW') and ticker.isdigit():
            ticker = f"{ticker}.TW"
        # 這裡呼叫 analyze
        return analyze(ticker)
    return render_template('index.html', watchlist=watchlist)

# 這裡不加快取，因為我們已經在內部的 get_cached_data 加過了
# 如果這裡再加，會變成雙重快取 (也不會怎樣，但沒必要)
def analyze(ticker):
    watchlist = Watchlist.query.all()
    
    # 1. 抓取資料 (🔥 呼叫有保護的函式)
    df, valid_ticker = get_cached_data(ticker)
    
    if df is None:
        return render_template('result.html', error=f"找不到股票 {ticker}", watchlist=watchlist)
    ticker = valid_ticker

    # 2. 技術分析
    is_breakout, tech_info = strategy.check_volume_breakout(df)
    
    # 3. 籌碼分析
    chip_data = chips.get_institutional_chips(ticker)
    
    # 4. 畫圖
    plot_div = chart.create_stock_chart(df, ticker)
    
    # 5. AI 分析
    stock_name = valid_ticker.replace('.TWO', '').replace('.TW', '')
    news = market_data.get_recent_news(stock_name)
    
    ai_score, ai_comment = sentiment.analyze_sentiment(
        stock_name=stock_name,
        news_list=news,
        tech_data=tech_info,  
        chip_data=chip_data   
    )

    # 6. ML & 回測 & 實戰訊號
    ml_prob = ml_predict.predict_next_day(df)
    backtest_result = backtest.run_backtest(df)
    is_buy, signal_msg = strategy.check_buy_signal(df)
    
    result = {
        "ticker": ticker,
        "price": tech_info.get('price', 'N/A'),
        "change_pct": tech_info.get('change_pct', 0),
        "vol_ratio": tech_info.get('vol_ratio', 0),
        "is_breakout": is_breakout,
        "rsi": tech_info.get('rsi', 50),
        "macd": tech_info.get('macd', 0),
        "macd_status": tech_info.get('macd_status', '無數據'),
        "ml_prob": ml_prob,
        "backtest": backtest_result,
        "ai_score": ai_score,
        "ai_comment": ai_comment,
        "signal": "強力買進" if is_buy else "觀望",
        "signal_msg": signal_msg,
        "chips": chip_data 
    }
    
    return render_template('result.html', result=result, plot_div=plot_div, watchlist=watchlist)

if __name__ == '__main__':
    app.run(debug=True, port=5000)