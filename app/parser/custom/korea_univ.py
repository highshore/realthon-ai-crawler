from datetime import datetime, timedelta
from urllib.parse import urljoin
import logging

LOG = logging.getLogger(__name__)

def parse_korea_univ_list(rows, page_url, interval_days, timezone):
    """
    기존의 parse_posts 로직: 고려대 전용 tr 태그 분석
    """
    today = datetime.now(timezone).date()
    cutoff = today - timedelta(days=interval_days - 1)
    
    posts = []
    for row in rows:
        cells = row.find_all("td")
        if not cells: continue
        
        # 날짜 파싱 (고려대 형식: YYYY.MM.DD)
        date_text = cells[-1].get_text(strip=True)
        try:
            row_date = datetime.strptime(date_text, "%Y.%m.%d").date()
        except ValueError:
            continue
            
        if row_date < cutoff: continue
            
        link_tag = row.select_one("a.article-title")
        if not link_tag: continue
            
        href = (link_tag.get("href") or "").replace("amp;", "")
        title = link_tag.get_text(strip=True)
        
        posts.append({
            "title": title, 
            "link": urljoin(page_url, href),
            "date": date_text
        })
    return posts

def get_korea_univ_content_area(soup):
    """
    기존 fetch_post_content의 본문 영역 탐색 로직
    """
    return soup.select_one(".view-con") or soup.select_one(".fr-view")