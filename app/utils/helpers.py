from urllib.parse import urlparse
from zoneinfo import ZoneInfo

TIMEZONE = ZoneInfo("Asia/Seoul")
from bs4 import BeautifulSoup

# app/utils/helpers.py
def is_valid_content(html: str) -> bool:
    if not html or len(html) < 5000: return False # 일단 기본 용량 체크
    soup = BeautifulSoup(html, "html.parser")
    
    # 1. '공지사항' 리스트가 들어갈 법한 영역 탐색
    # 서강대: .list-unit, 고려대: .board-list
    board_rows = soup.select("tr, li, .list-unit, .board-list tr")
    
    # 2. 링크 텍스트가 15자 이상인 '진짜 제목'이 몇 개나 되는지 확인
    valid_titles = []
    for row in board_rows:
        link = row.find("a")
        if link and len(link.get_text(strip=True)) > 15:
            valid_titles.append(link.get_text(strip=True))
            
    # 제목다운 게 3개도 안 나오면 이건 깡통 페이지라고 판단
    return len(valid_titles) >= 3
def guess_site_name(url: str) -> str:
    """URL 도메인을 분석해 사이트 이름을 추측합니다."""
    domain = urlparse(url).netloc
    mapping = {
        "sogang.ac.kr": "서강대학교 공지",
        "korea.ac.kr": "고려대학교 공지",
        "toss.im": "토스 채용 블로그",
    }
    for key, name in mapping.items():
        if key in domain: return name
    return domain.replace("www.", "").split('.')[0].capitalize()
def clean_for_ai(html: str) -> str:
    if not html: return ""
    soup = BeautifulSoup(html, "html.parser")

    # 1. 쓸데없는 태그 삭제
    for tag in soup(["script", "style", "path", "svg", "nav", "footer", "header", "noscript"]):
        tag.decompose()

    # 2. 모든 태그에서 'style', 'class', 'data-...' 속성 삭제 (이게 핵심!)
    for tag in soup.find_all(True):
        valid_attrs = {}
        # data-로 시작하는 모든 속성과 pkId 관련 단어가 포함된 속성을 다 챙겨!
        for attr, value in tag.attrs.items():
            if attr in ['href', 'id'] or 'pkid' in attr.lower() or 'id' in attr.lower():
                valid_attrs[attr] = value
        tag.attrs = valid_attrs
    clean_html = soup.prettify()
    return clean_html[:25000] # 너무 길면 자르기
def get_ai_friendly_html(html: str) -> str:
    if not html: return ""
    soup = BeautifulSoup(html, "html.parser")

    # 1. 아예 필요 없는 덩어리 날리기 (header, footer, nav 등)
    for noise in soup(["header", "footer", "nav", "script", "style", "aside"]):
        noise.decompose()

    # 2. 진짜 본문 영역(main이나 #contents)만 타겟팅
    main_area = soup.find("main") or soup.find(id="contents") or soup.find(id="__next") or soup
    
    # 3. 본문 영역 내에서 '공지 제목'일 가능성이 높은 <a> 태그만 추출
    # - 텍스트 길이가 10자 이상이거나
    # - 내부에 p, span, strong 태그가 있는 경우
    clean_soup = BeautifulSoup("<div></div>", "html.parser")
    target_div = clean_soup.div

    for a in main_area.find_all("a", href=True):
        title_text = a.get_text(strip=True)
        # 💡 [핵심 필터] 너무 짧은 메뉴명(로그인, 홈 등)은 버리고 진짜 제목 같은 놈만!
        if len(title_text) >= 10:
            # 새로운 깨끗한 <a> 태그 생성 (href만 남김)
            new_a = clean_soup.new_tag("a", href=a['href'])
            new_a.string = title_text
            target_div.append(new_a)

    return str(target_div)[:25000]