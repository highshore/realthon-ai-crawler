import json
import re
import os
from google import genai

# app/parser/ai_parser.py

def parse_with_ai(text_content, url, user_profile):
    interests = user_profile.get("interestFields", [])
    
    prompt = f"""
    당신은 채용 공고 추출 전문가입니다. 
    제공된 텍스트에서 유저의 관심사({interests})와 가장 잘 맞는 공고를 **최대 10개만** 찾아 JSON 배열로 응답하세요.
    데이터가 너무 많으면 가장 최신/중요한 것 위주로 선별하세요.

    [응답 스키마]:
    [
      {{
        "title": "공고명",
        "link": "ID 또는 URL",
        "date": "YYYY-MM-DD (모르면 빈칸)",
        "score": 0.0~1.0
      }}
    ]

    [주의]: JSON 외의 설명은 절대 금지하며, 문자열 내부에 쌍따옴표(")를 쓸 때는 반드시 이스케이프(\") 처리하세요.
    
    [텍스트]:
    {text_content[:12000]} # 👈 입력 텍스트도 1.2만 자로 제한해서 AI 부담 줄이기
    """

    try:
        client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=prompt,
            config={'response_mime_type': 'application/json'}
        )
        
        raw_text = response.text.strip()
        
        # 🚨 [방탄 로직 1] 마크다운 코드 블록(```json) 제거
        clean_json_str = re.sub(r"```json|```", "", raw_text).strip()
        
        # 🚨 [방탄 로직 2] 가끔 발생하는 trailing comma나 깨진 뒷부분 보정
        try:
            return json.loads(clean_json_str)
        except json.JSONDecodeError:
            # 정 안되면 대괄호 위치로 강제 슬라이싱 시도
            start_idx = clean_json_str.find("[")
            end_idx = clean_json_str.rfind("]")
            if start_idx != -1 and end_idx != -1:
                return json.loads(clean_json_str[start_idx:end_idx+1])
            raise

    except Exception as e:
        print(f"❌ AI 파싱 최종 실패: {e}")
        # 실패 로그에 AI가 뭐라고 뱉었는지 찍어보면 디버깅이 쉬워!
        # print(f"DEBUG: AI RAW RESPONSE: {response.text[:500]}")
        return []
    # app/parser/ai_parser.py

def summarize_content(content, user_profile):
    """
    본문 내용을 유저 관심사에 맞춰 3줄 요약합니다.
    """
    interests = user_profile.get("interestFields", [])
    
    # 🚨 본문이 너무 짧으면 요약할 필요가 없음
    if len(content) < 100:
        return content.strip()

    prompt = f"""
    당신은 커리어 컨설턴트입니다. 
    다음 채용/공지 본문을 유저의 관심사({interests})를 중심으로 핵심만 3줄 요약하세요.
    유저가 왜 이 공고를 읽어야 하는지 이유를 포함하세요.
    말투는 친절한 '~해요' 체를 사용하세요.

    [본문]
    {content[:4000]} 
    """
    
    try:
        from google import genai
        import os
        client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=prompt
        )
        return response.text.strip()
    except Exception as e:
        print(f"❌ 요약 중 에러: {e}")
        return content[:150].strip() + "..."
