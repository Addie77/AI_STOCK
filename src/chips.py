import requests
import pandas as pd
import datetime
import os

def get_institutional_chips(stock_id):
    """
    使用 FinMind API 抓取籌碼 (已加入雲端防擋機制)
    """
    # 1. 清洗代號
    clean_id = str(stock_id).replace(".TWO", "").replace(".TW", "").strip()
    
    print(f"💰 [籌碼系統] 正在抓取: {clean_id} (FinMind)")

    try:
        # 設定日期範圍 (抓最近 30 天，確保有足夠交易日)
        today = datetime.date.today()
        start_date = (today - datetime.timedelta(days=30)).strftime('%Y-%m-%d')
        
        url = "https://api.finmindtrade.com/api/v4/data"
        params = {
            "dataset": "TaiwanStockInstitutionalInvestorsBuySell", 
            "data_id": clean_id,                                 
            "start_date": start_date,
            "token": "" # 如果你有申請 FinMind Token，可以填在這裡，會更穩定
        }
        
        # 🔥【關鍵修正】加入 Headers 偽裝成瀏覽器
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json",
            "Referer": "https://finmindtrade.com/"
        }
        
        # 發送請求 (設定 timeout 避免卡死)
        r = requests.get(url, params=params, headers=headers, timeout=10)
        
        # 檢查 HTTP 狀態碼
        if r.status_code != 200:
            print(f"⚠️ FinMind 連線被拒 (Status: {r.status_code}) - 可能 IP 被擋")
            return default_empty_result()
            
        try:
            data = r.json()
        except ValueError:
            print(f"⚠️ FinMind 回傳非 JSON 格式 (可能是 HTML 錯誤頁面)")
            return default_empty_result()
        
        # 檢查 API 邏輯狀態
        if data.get('msg') != 'success':
            print(f"⚠️ API 回傳錯誤訊息: {data.get('msg')}")
            return default_empty_result()
            
        stock_data = data.get('data', [])
        
        if not stock_data:
            print(f"⚠️ {clean_id} 真實回傳為空 (API 正常但無數據)")
            return default_empty_result()

        # 轉成 DataFrame
        df = pd.DataFrame(stock_data)
        
        # 確保日期格式正確
        df['date'] = pd.to_datetime(df['date'])
        df = df.sort_values('date')
        
        # 取最近 5 個有交易的日期
        recent_days = df['date'].unique()[-5:]
        df_recent = df[df['date'].isin(recent_days)]
        
        # 初始化統計
        summary = {
            "foreign_total": 0,  # 外資
            "trust_total": 0,    # 投信
            "dealer_total": 0,   # 自營商
            "status_text": "無顯著變化"
        }

        # 資料表欄位: date, buy, sell, name
        for index, row in df_recent.iterrows():
            # FinMind 單位是股，除以 1000 換算成張
            net_buy = (row['buy'] - row['sell']) / 1000
            name = row['name']
            
            # 累加各法人買賣超
            if 'Foreign' in name: 
                summary['foreign_total'] += net_buy
            elif 'Investment_Trust' in name: 
                summary['trust_total'] += net_buy
            elif 'Dealer' in name: 
                summary['dealer_total'] += net_buy

        # 四捨五入取小數點第一位
        summary['foreign_total'] = round(summary['foreign_total'], 1)
        summary['trust_total'] = round(summary['trust_total'], 1)
        summary['dealer_total'] = round(summary['dealer_total'], 1)

        # 產生文字描述
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
        print(f"❌ [籌碼系統] 執行失敗: {e}")
        return default_empty_result()

def default_empty_result():
    return {
        "foreign_total": 0,
        "trust_total": 0,
        "dealer_total": 0,
        "status_text": "暫無法人數據"
    }