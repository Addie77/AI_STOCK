import requests
import pandas as pd
import datetime

def get_institutional_chips(stock_id):
    """
    直接使用 HTTP Request 抓取 FinMind API (修正代號清洗順序 Bug)
    """
    # 1. 清洗代號 (關鍵修正：先取代 .TWO，再取代 .TW)
    # 如果先取代 .TW，8436.TWO 會變成 8436O，導致查詢失敗
    clean_id = str(stock_id).replace(".TWO", "").replace(".TW", "").strip()
    
    print(f"💰 [籌碼系統] 正在抓取: {clean_id} (Direct API)")

    try:
        # 設定日期範圍 (抓最近 30 天)
        today = datetime.date.today()
        start_date = (today - datetime.timedelta(days=30)).strftime('%Y-%m-%d')
        
        # 直接呼叫 API 網址
        url = "https://api.finmindtrade.com/api/v4/data"
        params = {
            "dataset": "TaiwanStockInstitutionalInvestorsBuySell", 
            "data_id": clean_id,                                 
            "start_date": start_date,
            "token": "" 
        }
        
        # 發送請求
        r = requests.get(url, params=params)
        data = r.json()
        
        # 檢查 API 回傳狀態
        if data.get('msg') != 'success':
            print(f"⚠️ API 回傳錯誤訊息: {data.get('msg')}")
            return default_empty_result()
            
        stock_data = data.get('data', [])
        
        if not stock_data:
            print(f"⚠️ {clean_id} 真實回傳為空 (API 正常但無數據)")
            return default_empty_result()

        # 轉成 DataFrame
        df = pd.DataFrame(stock_data)
        
        df['date'] = pd.to_datetime(df['date'])
        df = df.sort_values('date')
        
        # 取最近 5 個有交易的日期
        recent_days = df['date'].unique()[-5:]
        df_recent = df[df['date'].isin(recent_days)]

        summary = {
            "foreign_total": 0,
            "trust_total": 0,
            "dealer_total": 0,
            "status_text": "無顯著變化"
        }

        # 資料表欄位: date, buy, sell, name
        for index, row in df_recent.iterrows():
            net_buy = (row['buy'] - row['sell']) / 1000
            name = row['name']
            
            if 'Foreign' in name: 
                summary['foreign_total'] += net_buy
            elif 'Investment_Trust' in name: 
                summary['trust_total'] += net_buy
            elif 'Dealer' in name: 
                summary['dealer_total'] += net_buy

        summary['foreign_total'] = round(summary['foreign_total'], 1)
        summary['trust_total'] = round(summary['trust_total'], 1)
        summary['dealer_total'] = round(summary['dealer_total'], 1)

        status = []
        if abs(summary['foreign_total']) > 50: 
            status.append(f"外資{'買超' if summary['foreign_total']>0 else '賣超'}")
        if abs(summary['trust_total']) > 10:
            status.append(f"投信{'買超' if summary['trust_total']>0 else '賣超'}")
        if abs(summary['dealer_total']) > 20:
             status.append(f"自營{'買超' if summary['dealer_total']>0 else '賣超'}")
            
        if not status:
            summary['status_text'] = "法人動作不大"
        else:
            summary['status_text'] = "，".join(status)
            
        print(f"   ↳ 成功！外資近5日: {summary['foreign_total']} 張")
        return summary

    except Exception as e:
        print(f"❌ [籌碼系統] 連線失敗: {e}")
        return default_empty_result()

def default_empty_result():
    return {
        "foreign_total": 0,
        "trust_total": 0,
        "dealer_total": 0,
        "status_text": "暫無法人數據"
    }