import yfinance as yf
import pandas as pd
from GoogleNews import GoogleNews

def get_stock_data(ticker_input):
    """
    抓取台股資料 (超強容錯版：自動修正 .TW/.TWO)
    """
    # 1. 清理輸入，轉大寫
    ticker_clean = str(ticker_input).strip().upper()
    print(f"📥 收到查詢: '{ticker_clean}'")

    # 2. 【關鍵修改】剝離代號 (Strip Suffix)
    # 不管使用者打 8436, 8436.TW, 還是 8436.TWO，我們都先還原成 "8436"
    base_ticker = ticker_clean.replace(".TWO", "").replace(".TW", "")
    
    # 3. 重建嘗試清單
    # 優先試 .TW (上市)，失敗就試 .TWO (上櫃)
    # 這樣就算使用者打錯 (如 8436.TW)，我們也能自動救回來抓到 8436.TWO
    tickers_to_try = [f"{base_ticker}.TW", f"{base_ticker}.TWO"]
    
    # (選用) 如果是美股代號 (如 NVDA)，上面加後綴會失敗，所以把原樣加回去當備案
    # 判斷方式：如果 base_ticker 不是純數字，可能是美股
    if not base_ticker.isdigit():
        tickers_to_try.append(base_ticker)

    print(f"📋 智慧嘗試清單: {tickers_to_try}")

    df = None
    successful_ticker = None

    for ticker in tickers_to_try:
        try:
            print(f"🔍 正在下載: {ticker} ...")
            
            stock = yf.Ticker(ticker)
            temp_df = stock.history(period="1y")

            # 檢查資料有效性
            if not temp_df.empty and len(temp_df) > 0:
                df = temp_df
                successful_ticker = ticker
                print(f"✅ 成功抓取: {successful_ticker} (資料筆數: {len(df)})")
                break # 成功抓到就收工
            else:
                print(f"⚠️ {ticker} 無資料，嘗試下一個...")

        except Exception as e:
            print(f"❌ 下載 {ticker} 發生錯誤: {e}")
            continue

    # 4. 結果回傳
    if df is None or successful_ticker is None:
        print("😭 全部嘗試失敗，找不到資料。")
        return None, None

    # --- 資料清洗 ---
    df.reset_index(inplace=True)

    required_cols = ['Date', 'Open', 'High', 'Low', 'Close', 'Volume']
    missing_cols = [c for c in required_cols if c not in df.columns]
    if missing_cols:
        return None, None

    if pd.api.types.is_datetime64_any_dtype(df['Date']):
        df['Date'] = df['Date'].dt.tz_localize(None)

    df['MA5_Vol'] = df['Volume'].rolling(window=5).mean()
    
    # 回傳資料表與「正確的代號」(例如使用者輸入 8436.TW，這裡會回傳 8436.TWO)
    return df, successful_ticker

def get_recent_news(stock_name):
    """
    抓取新聞 (維持不變)
    """
    try:
        googlenews = GoogleNews(lang='zh-TW', region='TW')
        googlenews.set_period('7d')
        clean_name = stock_name.replace('.TW', '').replace('.TWO', '')
        googlenews.search(clean_name)
        result = googlenews.result()
        headlines = [item['title'] for item in result[:10]]
        if not headlines:
            return ["近期無相關重大新聞"]
        return headlines
    except Exception as e:
        print(f"❌ 新聞抓取失敗: {e}")
        return ["新聞系統暫時異常"]