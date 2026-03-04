from bs4 import BeautifulSoup
from urllib.parse import urljoin
import json
import re
from datetime import datetime

from dotenv import load_dotenv
from app.utils.helpers import TIMEZONE
today = datetime.now(TIMEZONE).strftime('%Y-%m-%d')

load_dotenv() # 👈 이게 supabase 호출보다 위에 있는지 확인!
def parse_with_ai(html_content, base_url, user_profile):
    soup = BeautifulSoup(html_content, "html.parser")
    
    # Extract user interests from profile
    interests = user_profile.get("interests", "관심사 정보 없음") if user_profile else "관심사 정보 없음"
    
    # [STEP 1] 메뉴, 헤더, 푸터 등 쓰레기 데이터는 아예 삭제 (Decompose)
    for trash in soup.select("header, footer, nav, .menu, .gnb, #sidebar, .aside"):
        trash.decompose()

    candidates = []
    
    # [STEP 2] 진짜 게시판 목록이 있을 법한 컨테이너만 타겟팅
    # 고려대/일반 게시판의 본문 영역 클래스들
    board_container = soup.select_one(".board-list, .list-table, #content, main, .view-con")
    target_soup = board_container if board_container else soup

    # [STEP 3] 해당 영역 안에서만 tr 또는 li 탐색
    rows = target_soup.select("tr, li")
    
    for row in rows:
        link_tag = row.select_one("a")
        if not link_tag or not link_tag.get("href"):
            continue
            
        href = link_tag.get("href").replace("amp;", "")
        # 자바스크립트 링크나 메뉴 링크 제외
        if "javascript" in href or len(href) < 5:
            continue
            
        title = link_tag.get_text(strip=True)
        # 날짜도 대충 근처 td에서 가져오기 (없으면 오늘 날짜)
        date_tag = row.find_all("td")[-1] if row.find_all("td") else None
        date_text = date_tag.get_text(strip=True) if date_tag else today
        
        # 상대경로 보정
        full_link = urljoin(base_url, href)
        
        if len(title) > 5: # 제목다운 것만 추가
            candidates.append({
                "title": title,
                "link": full_link,
                "date": date_text
            })

    if not candidates:
        return []

    # [STEP 2] 정제된 리스트만 AI에게 던져서 점수 매기기 (토큰 절약 + 정확도 폭발)
    candidates_json = json.dumps(candidates, ensure_ascii=False)
    
    prompt = f"""
    당신은 공지사항 선별 전문가입니다. 아래 제공된 공지사항 목록(JSON)을 보고, 
    유저의 관심사({interests})와 관련이 깊은 항목에 점수를 매기세요.

    [목록]
    {candidates_json}

    [규칙]
    1. 제공된 JSON의 'link'와 'title'을 절대 수정하지 마세요.
    2. 유저 관심사와 맞으면 score를 0.5~1.0, 아니면 0.0~0.4로 매기세요.
    3. 날짜 형식을 'YYYY-MM-DD'로 깔끔하게 정리하세요.

    반드시 JSON 배열 형태로만 응답하세요.
    """

    try:
        from google import genai
        import os
        client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=prompt
        )
        
        match = re.search(r"\[.*\]", response.text, re.DOTALL)
        if match:
            return json.loads(match.group(0))
        return []
    except Exception as e:
        print(f"❌ AI 평가 실패: {e}")
        # AI가 실패하면 점수 없이 리스트라도 반환 (백업)
        return candidates