import plotly.graph_objects as go
from plotly.subplots import make_subplots # 引入子圖功能
import pandas as pd

def create_stock_chart(df, ticker):
    """
    繪製專業互動式 K 線圖
    包含：
    1. 主圖：K線 + 月線(MA20) + 季線(MA60)
    2. 副圖：成交量 (Volume)
    3. 自動修復日期格式與補算指標
    """
    
    # --- 1. 資料清洗與日期鎖定 ---
    df = df.copy()
    
    # 處理日期索引 (避免 1970 問題)
    if 'Date' in df.columns:
        df['Date'] = pd.to_datetime(df['Date'])
        df.set_index('Date', inplace=True)
    
    try:
        df.index = pd.to_datetime(df.index)
    except:
        pass

    # --- 2. [關鍵] 強制補算均線 (如果資料裡沒有的話) ---
    # 這樣保證線一定畫得出來！
    if 'MA20' not in df.columns:
        df['MA20'] = df['Close'].rolling(window=20).mean()
    if 'MA60' not in df.columns:
        df['MA60'] = df['Close'].rolling(window=60).mean()

    # --- 3. 建立雙層圖表 (上層股價，下層成交量) ---
    fig = make_subplots(
        rows=2, cols=1, 
        shared_xaxes=True, # 共用時間軸 (放大縮小會同步)
        vertical_spacing=0.03, # 上下圖的間距
        row_heights=[0.7, 0.3], # 上圖佔 70%，下圖佔 30%
        specs=[[{"secondary_y": False}], [{"secondary_y": False}]]
    )

    # --- 4. 繪製主圖 (Row 1) ---
    
    # A. K 線
    fig.add_trace(go.Candlestick(
        x=df.index,
        open=df['Open'], high=df['High'],
        low=df['Low'], close=df['Close'],
        name='K線',
        increasing_line_color='#e53935', # 紅
        decreasing_line_color='#00c853'  # 綠
    ), row=1, col=1)

    # B. 均線 (月線 & 季線)
    # 因為前面已經強制補算了，所以這裡直接畫，不用怕沒有
    fig.add_trace(go.Scatter(
        x=df.index, y=df['MA20'],
        mode='lines', name='月線 (20MA)',
        line=dict(color='orange', width=1.5)
    ), row=1, col=1)

    fig.add_trace(go.Scatter(
        x=df.index, y=df['MA60'],
        mode='lines', name='季線 (60MA)',
        line=dict(color='blue', width=1.5)
    ), row=1, col=1)

    # --- 5. 繪製副圖 (Row 2) - 成交量 ---
    
    # 設定成交量顏色：漲是紅，跌是綠
    colors = ['#e53935' if row['Open'] < row['Close'] else '#00c853' for index, row in df.iterrows()]

    fig.add_trace(go.Bar(
        x=df.index,
        y=df['Volume'],
        name='成交量',
        marker_color=colors, # 柱子顏色
        opacity=0.5          # 半透明才不會太搶眼
    ), row=2, col=1)

    # --- 6. 佈局優化 ---
    chart_title = f'{ticker} 個股詳情' if ticker else '個股詳情'
    
    fig.update_layout(
        title=chart_title,
        yaxis_title='價格',
        yaxis2_title='成交量', # 第二個 Y 軸的標題
        template='plotly_white',
        showlegend=True,
        height=600, # 高度拉高一點，因為有兩層
        margin=dict(l=50, r=20, t=50, b=20),
        
        # X 軸設定 (隱藏假日)
        xaxis=dict(
            type='date',
            tickformat='%Y-%m-%d',
            rangebreaks=[dict(bounds=["sat", "mon"])]
        ),
        # 下方 X 軸也要設定 (成交量那層)
        xaxis2=dict(
            type='date',
            tickformat='%Y-%m-%d',
            rangebreaks=[dict(bounds=["sat", "mon"])]
        ),
        
        # 關閉原本醜醜的拉霸
        xaxis_rangeslider_visible=False,
        hovermode='x unified'
    )

    # 回傳 HTML
    chart_html = fig.to_html(full_html=False, include_plotlyjs='cdn')
    return chart_html