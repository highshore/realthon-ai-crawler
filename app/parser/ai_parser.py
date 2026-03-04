import json
import re
import os
from google import genai

def parse_with_ai(html_content, base_url, user_profile):
    interests = user_profile.get("interests", [])
    if isinstance(interests, list):
        interests = ", ".join(interests)

    # 1. AI에게 줄 데이터 요약 (토큰 절약 및 구조화)
    prompt = f"""
    당신은 채용/공지사항 JSON 변환기입니다. 
    제공된 HTML에서 유저 관심사({interests})와 관련된 공고를 추출해 JSON 배열로만 응답하세요.

    [필수 스키마]:
    [
      {{
        "title": "공고 제목",
        "link": "URL 또는 ID 숫자",
        "date": "YYYY-MM-DD",
        "score": 0.0~1.0
      }}
    ]

    [주의사항]:
    - 관련이 적어도 리스트 형태면 모두 포함하되 score만 낮게 책정할 것.
    - JSON 외에 설명이나 주석은 절대 금지.
    - link가 없으면 해당 항목의 고유 ID(숫자)라도 넣을 것.

    [HTML]:
    {html_content[:15000]} 
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