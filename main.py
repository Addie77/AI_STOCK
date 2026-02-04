import pandas as pd
from datetime import datetime
import config
from src import market_data, strategy, sentiment

def main():
    print(f"🚀 AI 智能投資系統啟動... (模型: {config.AI_MODEL_NAME})")
    print(f"📋 監控清單: {config.TARGET_STOCKS}")
    print("-" * 50)

    report_data = []

    # 1. 遍歷每一支股票
    for ticker in config.TARGET_STOCKS:
        print(f"🔍 正在檢查 {ticker} ... ", end="")
        
        # A. 抓取股價
        df = market_data.get_stock_data(ticker)
        if df is None:
            print("❌ 資料抓取失敗")
            continue

        # B. 技術面篩選 (量能突破)
        is_breakout, tech_info = strategy.check_volume_breakout(df)
        
        if not is_breakout:
            print("💤 無訊號 (跳過)")
            continue # 如果沒突破，直接跳過，節省 AI 資源
            
        print("🔥 發現技術面突破！啟動 AI 分析...")

        # C. 抓取新聞 & D. AI 情感分析
        # 這裡簡單把 .TW 去掉當作關鍵字 (例如 2330.TW -> 2330)
        stock_name = ticker.split(".")[0] 
        news = market_data.get_recent_news(stock_name)
        
        ai_score, ai_comment = sentiment.analyze_sentiment(stock_name, news)
        
        # E. 綜合判斷
        final_signal = "觀察"
        if ai_score >= config.SENTIMENT_THRESHOLD:
            final_signal = "強力買進 (Strong Buy)"
        elif ai_score <= -0.2:
            final_signal = "假突破疑慮 (Fakeout)"
            
        print(f"   🤖 AI 情緒分: {ai_score} | 評語: {ai_comment}")
        print(f"   👉 最終建議: {final_signal}")

        # F. 收集結果
        report_data.append({
            "Stock": ticker,
            "Date": datetime.now().strftime("%Y-%m-%d"),
            "Price": tech_info['price'],
            "Change(%)": tech_info['change_pct'],
            "Vol_Ratio": tech_info['vol_ratio'],
            "AI_Score": ai_score,
            "AI_Comment": ai_comment,
            "Signal": final_signal
        })
        print("-" * 30)

    # 2. 輸出報表
    if report_data:
        df_result = pd.DataFrame(report_data)
        filename = f"data/report_{datetime.now().strftime('%Y%m%d')}.csv"
        df_result.to_csv(filename, index=False, encoding="utf-8-sig")
        print(f"\n✅ 分析完成！報表已儲存至: {filename}")
        print(df_result[["Stock", "Price", "AI_Score", "Signal"]])
    else:
        print("\n🍂 今日無任何股票符合「量能突破」條件。")

if __name__ == "__main__":
    main()