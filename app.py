from flask import Flask, render_template, request, redirect, url_for, abort
from flask_sqlalchemy import SQLAlchemy
from GoogleNews import GoogleNews
import google.generativeai as genai
from pytz import timezone
import os
import datetime

# --- 引入 LINE Bot 相關套件 ---
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage

# --- [新增] 引入排程套件 ---
from apscheduler.schedulers.background import BackgroundScheduler
import atexit

# 引入你的功能模組
from src import market_data, strategy, chart, chips, ml_predict, backtest, sentiment
from config import Config 

app = Flask(__name__)
app.config.from_object(Config)

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
#  PART 1: 定時推播任務 (新增!)
# ===========================

def send_morning_report():
    """ 每天早上執行的任務：掃描自選股並推播 """
    # 1. 取得使用者 ID (從 .env 讀取)
    user_id = os.getenv('ADMIN_USER_ID')
    if not user_id:
        print("❌ 尚未設定 ADMIN_USER_ID，無法推播")
        return

    print("⏰ 開始執行每日早報推播...")
    
    # 2. 讀取資料庫中的自選股
    # 注意：這裡要用 app.app_context() 因為是在背景執行
    with app.app_context():
        watchlist = Watchlist.query.all()
        if not watchlist:
            try:
                line_bot_api.push_message(user_id, TextSendMessage(text="早安！目前自選清單是空的，趕快加入股票吧！"))
            except:
                pass
            return

        report_content = "🌞 早安！您的自選股快報：\n"
        
        # 3. 逐一分析每一檔股票
        for stock in watchlist:
            try:
                ticker = stock.ticker
                df, valid_ticker = market_data.get_stock_data(ticker)
                
                if df is not None:
                    # 簡單判斷漲跌
                    today = df.iloc[-1]
                    price = round(today['Close'], 2)
                    change_pct = round(((today['Close'] - df['Close'].iloc[-2]) / df['Close'].iloc[-2]) * 100, 2)
                    
                    # 加上 emoji
                    emoji = "🔴" if change_pct > 0 else "🟢" if change_pct < 0 else "⚪"
                    
                    report_content += f"{emoji} {valid_ticker.replace('.TW','')}: {price} ({change_pct}%)\n"
            except Exception as e:
                print(f"分析 {stock.ticker} 失敗: {e}")

        report_content += "\n💡 輸入股票代號可查看詳細 AI 分析！"

        # 4. 發送推播
        try:
            line_bot_api.push_message(user_id, TextSendMessage(text=report_content))
            print("✅ 早報推播成功！")
        except Exception as e:
            print(f"❌ 推播失敗: {e}")

# 啟動排程器
if not app.debug or os.environ.get('WERKZEUG_RUN_MAIN') == 'true':
    tw_timezone = timezone('Asia/Taipei') 
    scheduler = BackgroundScheduler(timezone=tw_timezone)
    # 設定每天早上 09:00 執行 (或是你可以改成現在的時間+2分鐘來測試)
    # 測試時可以把 hour, minute 改成當下時間來驗證
    scheduler.add_job(func=send_morning_report, trigger="cron", hour=9, minute=0)
    
    # [測試用] 如果你想立刻測試推播，把下面這行取消註解 (程式一啟動就會發)
    #scheduler.add_job(func=send_morning_report, trigger="date", run_date=datetime.datetime.now() + datetime.timedelta(seconds=10))
    
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
    
    # 簡易後門：讓你在 LINE 裡面輸入 "ID" 就可以查詢自己的 User ID
    if user_msg.upper() == "ID":
        user_id = event.source.user_id
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"您的 User ID 是：\n{user_id}\n(請貼到 .env 檔案中)"))
        return

    if user_msg.isdigit() or user_msg.upper().endswith('.TW'):
        ticker = user_msg if user_msg.upper().endswith('.TW') else f"{user_msg}.TW"
        
        try:
            df, valid_ticker = market_data.get_stock_data(ticker)
            if df is None:
                line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"❌ 找不到 {ticker}"))
                return

            is_breakout, tech_info = strategy.check_volume_breakout(df)
            price = tech_info['price']
            change = tech_info['change_pct']
            vol_ratio = tech_info['vol_ratio']
            
            stock_name = valid_ticker.replace('.TWO', '').replace('.TW', '')
            news = market_data.get_recent_news(stock_name)
            
            model_name = app.config.get('GEMINI_MODEL_NAME')
            model = genai.GenerativeModel(model_name)
            
            news_text = "\n".join([f"- {n}" for n in news]) if news else "無重大新聞"
            
            prompt = f"""
            你是一位台股分析師。請用繁體中文針對「{stock_name}」給出 50 字以內的簡評。
            數據：現價 {price} (漲幅 {change}%)，爆量 {vol_ratio} 倍。
            新聞：{news_text}
            """
            
            response = model.generate_content(prompt)
            ai_comment = response.text.strip()

            result_msg = (
                f"📊 【{stock_name}】\n"
                f"💰 {price} ({change}%)\n"
                f"📈 {'🔥 爆量' if is_breakout else '🐢 盤整'}\n"
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
#  PART 3: 網頁路由 (維持原本)
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
        return analyze(ticker)
    return render_template('index.html', watchlist=watchlist)

def analyze(ticker):
    watchlist = Watchlist.query.all()
    
    # 1. 抓取資料
    df, valid_ticker = market_data.get_stock_data(ticker)
    if df is None:
        return render_template('result.html', error=f"找不到股票 {ticker}", watchlist=watchlist)
    ticker = valid_ticker

    # 2. 技術分析 (這裡會取得 RSI, MACD 等數據)
    is_breakout, tech_info = strategy.check_volume_breakout(df)
    
    # 3. 籌碼分析
    chip_data = chips.get_institutional_chips(ticker)
    
    # 4. 畫圖
    plot_div = chart.create_stock_chart(df, ticker)
    
    # 5. AI 分析 (傳入所有數據！)
    stock_name = valid_ticker.replace('.TWO', '').replace('.TW', '')
    news = market_data.get_recent_news(stock_name)
    
    # [關鍵修改] 傳入 tech_info 和 chip_data 讓 AI 參考
    ai_score, ai_comment = sentiment.analyze_sentiment(
        stock_name=stock_name,
        news_list=news,
        tech_data=tech_info,  # 包含 RSI, MACD, Price
        chip_data=chip_data   # 包含三大法人買賣超
    )

    # 6. ML & 回測
    ml_prob = ml_predict.predict_next_day(df)
    backtest_result = backtest.run_backtest(df)
    
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
        "signal": "強力買進" if (is_breakout and ai_score > 0.3) else "觀望",
        "chips": chip_data 
    }
    
    return render_template('result.html', result=result, plot_div=plot_div, watchlist=watchlist)

if __name__ == '__main__':
    app.run(debug=True, port=5000)