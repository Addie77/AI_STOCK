import google.generativeai as genai
import re
import os
import time
from dotenv import load_dotenv
from flask import current_app

def analyze_sentiment(stock_name, news_list, tech_data, chip_data=None):
    """
    綜合分析：新聞 + 籌碼 + 技術指標
    策略：改用「純文字解析」模式，解決 JSON 格式導致的字數限制與報錯問題。
    """
    # 1. 獲取 API Key
    api_key = current_app.config.get('GOOGLE_API_KEY')
    if not api_key:
        load_dotenv()
        api_key = os.getenv('GOOGLE_API_KEY')

    if not api_key:
        return 0, "系統錯誤：未設定 API Key"

    # 使用你指定的 gemini-2.5-flash
    model_name = current_app.config.get('GEMINI_MODEL_NAME')
    if not model_name:
        model_name = 'gemini-1.5-flash' # 保底

    genai.configure(api_key=api_key)

    # 2. 準備數據
    news_text = "\n".join(news_list) if news_list else "近期無重大新聞"
    
    chip_info = "無籌碼數據"
    if chip_data:
        chip_info = f"""
        - 外資: {chip_data.get('foreign_total', 0)} 張
        - 投信: {chip_data.get('trust_total', 0)} 張
        - 狀態: {chip_data.get('status_text', '無')}
        """

    # 3. Prompt (改為純文字格式要求)
    # 我們不求 JSON 了，直接叫它一行一行寫出來，這樣最穩！
    prompt = f"""
    你是一位嚴格的台股分析師。請根據數據進行評分。
    
    【評分邏輯】：
    1. 利多+技術強+法人買 -> 0.8 (強多)
    2. 利空+破線+外資賣 -> -0.8 (強空)
    3. 盤整+無量 -> 0.0 (觀望)
    4. 利多不漲+籌碼亂 -> -0.4 (偏空)

    【目標】：{stock_name}
    [技術]: 現價 {tech_data.get('price')}, RSI {tech_data.get('rsi')}, MACD {tech_data.get('macd_status')}, 爆量 {"是" if tech_data.get('is_breakout') else "否"}
    [籌碼]: {chip_info}
    [新聞]: {news_text}
    
    請務必依照以下格式回傳 (不要加 Markdown，不要加 JSON)：
    分數：[請填數值]
    評論：[請填寫100字以內的完整繁體中文分析]
    """

    print(f"🧐 [Sentiment] 正在分析 {stock_name} (Model={model_name})")

    # 4. 設定參數
    # 這裡我們只設定溫度 (0.1 保持理性)，但不設定 max_output_tokens
    # 讓模型自己決定要講多少字，這樣就不會被腰斬了！
    my_config = {
        "temperature": 0.1, 
        "top_p": 0.95,
        "top_k": 40
    }

    max_retries = 3
    for attempt in range(max_retries):
        try:
            model = genai.GenerativeModel(model_name)
            
            response = model.generate_content(prompt, generation_config=my_config)
            text = response.text.strip()
            
            # 5. 純文字解析邏輯 (比 JSON 強壯100倍)
            final_score = 0
            final_comment = "AI 未提供評論"
            
            # 找分數 (支援 "分數：" 或 "分數:")
            score_match = re.search(r"分數[:：]\s*([-+]?\d*\.?\d+)", text)
            if score_match:
                try:
                    final_score = float(score_match.group(1))
                except: pass
            
            # 找評論 (抓取 "評論：" 後面的所有文字)
            comment_match = re.search(r"評論[:：]\s*(.*)", text, re.DOTALL)
            if comment_match:
                final_comment = comment_match.group(1).strip()
            
            # 如果還是沒抓到，就直接回傳整段文字，至少讓使用者看得到東西
            if final_comment == "AI 未提供評論" and len(text) > 5:
                final_comment = text

            return final_score, final_comment

        except Exception as e:
            print(f"⚠️ [Sentiment] 錯誤 (第 {attempt+1} 次): {e}")
            if attempt == max_retries - 1:
                return 0, f"分析失敗: {str(e)}"
            time.sleep(2)
    
    return 0, "AI 系統忙碌中"