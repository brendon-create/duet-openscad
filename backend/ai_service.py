# ai_service.py - DUET AI 諮詢服務

import anthropic
import json
import re
import os

# API Key - 使用環境變量
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

# Initialize Anthropic client
client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

# System Prompt (基於問卷分析設計)
SYSTEM_PROMPT = """你是 BCAG 訂製珠寶的資深設計師，擁有超過 20 年的客製化珠寶諮詢經驗。
你正在為 DUET 系列（雙字母交織墜飾）進行設計諮詢。

【重要】你必須使用繁體中文（台灣用語）與顧客對話。不可使用簡體中文。

【你的角色與風格】
- 你是一位溫暖、專業的設計師，善於傾聽並引導顧客發掘設計的深層意義
- 你的對話自然、有同理心，不會過於正式或冷淡
- 你會根據顧客的回答深度，自然決定是否追問或進入下一題

【核心諮詢問題】（必須依序完成）
1. 這件 DUET 作品是要送給誰的？
2. 請選擇兩個英文字母，它們各代表什麼意義？
3. 能分享一個你們之間印象最深刻的時刻嗎？
4. 認識對方之前和之後，你的生命有了什麼不同？
5. 對方在你生命中為什麼這麼重要？
6. 如果用三個詞描述你們的關係，會是什麼？
7. 你希望透過這件作品向對方傳達什麼？
8. 你希望對方在什麼場合佩戴這件作品？

【追問原則】
- 如果回答很簡短（<10字），自然地追問細節。例如：
  顧客說「我女友」→ 你問「你們在一起多久了呢？」
  
- 如果提到具體事件但未展開，邀請分享。例如：
  顧客說「第一次約會時我超緊張」→ 你問「那這麼緊張的你們，有沒有做了什麼蠢事或發生什麼印象深刻的事情？」
  
- 如果回答已經很詳細、真誠（>50字），給予認可和共鳴，然後進入下一題。例如：
  「這真的很動人，謝謝你這麼真誠的分享。接下來...」
  
- 如果顧客只給一個字的答案，換個角度問。例如：
  顧客說「愛」→ 你問「有沒有一句話或一個畫面，能代表這份愛？」

【重要限制】
- 每個核心問題最多追問 2 次，不要過度追問
- 總對話輪數控制在 10-15 輪
- 不要問開放式問題，給予具體引導
- 保持自然對話節奏，不要像在填表單

【對話範例】
好的範例：
顧客：「我女友」
你：「太好了！你們在一起多久了呢？」

不好的範例：
顧客：「我女友」
你：「請問您的女友對您來說有什麼特別的意義嗎？」（太正式）

【完成後】
當完成所有核心問題後，說：
「謝謝你的分享！我已經充分了解了。接下來我會根據你的故事，為你推薦最適合的字體組合。」

然後輸出 JSON 格式：
{
  "conversation_summary": "簡短摘要",
  "emotional_keywords": ["關鍵詞1", "關鍵詞2", ...],
  "relationship_type": "伴侶/親子/友人",
  "style_hints": ["溫柔", "現代", "優雅", ...],
  "letters": {"letter1": "B", "letter2": "R"}
}
"""

# 精選字體列表（基於問卷分析，20種代表性字體）
CURATED_FONTS = {
    "elegant_serif": ["Playfair Display", "Cormorant Garamond", "EB Garamond", "DM Serif Text"],
    "modern_sans": ["Montserrat", "Poppins", "Jost", "Outfit"],
    "handwritten": ["Allura", "Alex Brush", "Sacramento", "Great Vibes", "Dancing Script"],
    "display": ["Abril Fatface", "Bebas Neue", "Audiowide", "Cinzel"],
    "geometric": ["Advent Pro", "Space Grotesk", "Orbitron"]
}

ALL_FONTS = [font for category in CURATED_FONTS.values() for font in category]


def process_ai_chat(conversation_history):
    """
    處理 AI 對話
    """
    try:
        # 呼叫 Claude API
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1000,
            system=SYSTEM_PROMPT,
            messages=conversation_history
        )
        
        ai_message = response.content[0].text
        
        # 檢查是否完成對話（尋找 JSON 輸出）
        if "{" in ai_message and "}" in ai_message:
            # 提取 JSON
            json_start = ai_message.find("{")
            json_end = ai_message.rfind("}") + 1
            json_str = ai_message[json_start:json_end]
            
            try:
                summary = json.loads(json_str)
                
                # 生成字體推薦
                recommended_fonts = recommend_fonts(summary)
                
                return {
                    "completed": True,
                    "summary": summary,
                    "recommended_fonts": recommended_fonts,
                    "letters": summary.get("letters", {}),
                    "emotional_keywords": summary.get("emotional_keywords", [])
                }
            except json.JSONDecodeError:
                pass
        
        # 未完成，繼續對話
        return {
            "completed": False,
            "message": ai_message
        }
        
    except Exception as e:
        print(f"AI Chat Error: {e}")
        return {
            "completed": False,
            "message": "抱歉，發生了一些問題。請稍後再試。"
        }


def recommend_fonts(summary):
    """
    根據對話摘要推薦字體
    基於問卷分析的邏輯
    """
    style_hints = summary.get("style_hints", [])
    emotional_keywords = summary.get("emotional_keywords", [])
    relationship_type = summary.get("relationship_type", "")
    
    # 情感關鍵詞映射
    keyword_map = {
        "溫柔": "handwritten",
        "優雅": "elegant_serif",
        "現代": "modern_sans",
        "活潑": "display",
        "簡約": "modern_sans",
        "經典": "elegant_serif",
        "科技": "geometric",
        "力量": "display",
        "浪漫": "handwritten"
    }
    
    # 根據關鍵詞選擇字體類別
    categories = []
    for keyword in emotional_keywords + style_hints:
        for key, cat in keyword_map.items():
            if key in keyword:
                categories.append(cat)
    
    # 如果沒有匹配，使用默認推薦（基於關係類型）
    if not categories:
        if "伴侶" in relationship_type:
            categories = ["handwritten", "elegant_serif"]
        elif "親子" in relationship_type:
            categories = ["modern_sans", "elegant_serif"]
        else:
            categories = ["elegant_serif", "modern_sans"]
    
    # 選擇字體
    font1_category = categories[0] if categories else "handwritten"
    font2_category = categories[1] if len(categories) > 1 else "modern_sans"
    
    # 確保兩個字體來自不同類別（形成對比）
    if font1_category == font2_category:
        if font1_category == "handwritten":
            font2_category = "modern_sans"
        else:
            font2_category = "handwritten"
    
    font1 = CURATED_FONTS[font1_category][0]
    font2 = CURATED_FONTS[font2_category][0]
    
    # 生成推薦理由
    reason_templates = {
        "handwritten": "優雅柔美的手寫字體，適合表達溫柔與浪漫的情感",
        "elegant_serif": "經典襯線體，展現永恆與優雅的氣質",
        "modern_sans": "現代簡約字體，呈現俐落與當代美感",
        "display": "粗獷有力的展示字體，象徵堅定與力量",
        "geometric": "幾何造型字體，展現科技感與前衛精神"
    }
    
    return {
        "font1": font1,
        "font1_reason": reason_templates.get(font1_category, "適合您的設計風格"),
        "font2": font2,
        "font2_reason": reason_templates.get(font2_category, "與第一個字母形成完美對比")
    }


def generate_design_concept(conversation_history, selected_fonts, letters):
    """
    生成設計理念
    基於完整對話和最終選定的字體
    """
    try:
        # 準備 prompt
        concept_prompt = f"""
基於以下顧客的對話內容，為他們的 DUET 訂製珠寶創作一段溫馨、真誠的設計理念。

對話摘要：
{json.dumps(conversation_history, ensure_ascii=False, indent=2)}

最終設計：
- 字母：{letters['letter1']} + {letters['letter2']}
- 字體：{selected_fonts['font1']} × {selected_fonts['font2']}

請創作約 150-200 字的設計理念，包含：
1. 標題（用《》包裹，3-6個字）
2. 字母意義的詮釋
3. 字體選擇的象徵意義
4. 引用顧客分享的故事或情感
5. 作品的精神內涵

風格要求：
- 溫暖、真誠、有詩意
- 避免陳腔濫調
- 融入顧客的真實故事
- 讓人感動但不矯情

請直接輸出設計理念文案，不需要其他說明。
"""
        
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=800,
            messages=[{
                "role": "user",
                "content": concept_prompt
            }]
        )
        
        concept_text = response.content[0].text.strip()
        
        return {
            "success": True,
            "concept": concept_text
        }
        
    except Exception as e:
        print(f"Design Concept Error: {e}")
        return {
            "success": False,
            "error": str(e)
        }


# Flask API 端點（添加到 app.py）
"""
from ai_service import process_ai_chat, generate_design_concept

@app.route('/api/ai-chat', methods=['POST'])
def api_ai_chat():
    data = request.json
    conversation_history = data.get('conversation_history', [])
    
    result = process_ai_chat(conversation_history)
    
    return jsonify(result)


@app.route('/api/generate-design-concept', methods=['POST'])
def api_generate_design_concept():
    data = request.json
    
    conversation_history = data.get('conversation', [])
    selected_fonts = data.get('selectedFonts', {})
    letters = data.get('letters', {})
    
    result = generate_design_concept(conversation_history, selected_fonts, letters)
    
    return jsonify(result)
"""
