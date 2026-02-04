import google.generativeai as genai
import os
from dotenv import load_dotenv

# 載入 API Key
load_dotenv()
api_key = os.getenv("GOOGLE_API_KEY")
genai.configure(api_key=api_key)

print("🔍 正在查詢你的帳號可用模型清單...\n")

try:
    for m in genai.list_models():
        if 'generateContent' in m.supported_generation_methods:
            print(f"✅ API 代號: {m.name}")
            print(f"   顯示名稱: {m.display_name}")
            print("-" * 30)
except Exception as e:
    print(f"❌ 查詢失敗: {e}")