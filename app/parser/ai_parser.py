import os
import json
import re
from google import genai

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

def parse_with_ai(content, base_url, user_profile):
    interests = ", ".join(user_profile.get("interestFields", []))
    
    prompt = f"""
    당신은 웹페이지 분석 전문가입니다. 제공된 텍스트에서 공지사항 목록을 찾아 JSON 배열로 반환하세요.
    사용자 관심분야: {interests}
    
    [응답 형식]
    [
      {{"title": "제목", "link": "전체URL", "score": 0.0~1.0, "summary": "관심분야 중심 1문장 요약"}}
    ]
    
    내용:
    {content[:15000]}
    """
    
    try:
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=prompt
        )
        # JSON 배열 추출 로직
        match = re.search(r"\[.*\]", response.text, re.DOTALL)
        return json.loads(match.group(0)) if match else []
    except Exception as e:
        print(f"AI 파싱 실패: {e}")
        return []