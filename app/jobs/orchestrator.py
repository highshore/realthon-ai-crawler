import logging
import re
from datetime import datetime, timedelta
from urllib.parse import urljoin, urlparse
from app.engine.static_fetcher import fetch_static
from app.engine.dynamic_fetcher import fetch_dynamic
from app.parser.ai_parser import parse_with_ai
from app.utils.helpers import TIMEZONE,  get_ai_friendly_html,  is_valid_content
from markdownify import markdownify as md
from app.utils.helpers import get_ai_friendly_html

LOG = logging.getLogger(__name__)

def get_clean_base_url(url):
    # .do로 끝나는 경로 처리 (예: .../notice_under.do -> .../)
    parsed = urlparse(url)
    path = parsed.path
    if path.endswith('.do'):
        path = path[:path.rfind('/') + 1]
    return f"{parsed.scheme}://{parsed.netloc}{path}"
async def run(event):
    user_profile = event.get("userProfile", {})
    target_urls = event.get("targetUrls") or [event.get("targetUrl")]
    interval_days = int(user_profile.get("intervalDays", 3))
    cutoff_date = (datetime.now(TIMEZONE) - timedelta(days=interval_days)).date()

    all_notices = []

    for url in target_urls:
        if not url: continue
        
        # [STEP 1] 목록 수집 (정적 -> 부실하면 동적)
        LOG.info(f"⚡ [STEP 1] 목록 수집 시도: {url}")
        list_html = fetch_static(url)
        is_dynamic_used = False

        # 알맹이 체크 (is_valid_content 사용)
        if not list_html or not is_valid_content(list_html):
            LOG.warning(f"⚠️ 정적 데이터 부실. 즉시 동적(Dynamic) 전환.")
            list_html = await fetch_dynamic(url)
            is_dynamic_used = True

        if not list_html:
            LOG.error(f"❌ 목록 수집 실패: {url}")
            continue

        # [STEP 2] AI 분석 (정제된 텍스트 전달)
        # 💡 처음부터 정제해서 주는 게 AI가 훨씬 잘 알아먹어!
        clean_text = get_ai_friendly_html(list_html)
        LOG.info(f"🧹 텍스트 정제 완료 (글자수: {len(clean_text)})")
        
        notices = parse_with_ai(clean_text, url, user_profile)

        # 🚨 [재시도 로직] 결과가 0건일 때
        if not notices:
            if not is_dynamic_used:
                LOG.warning(f"🔍 1차(정적) 분석 0건 -> 2차(동적) 재시도 수행")
                list_html = await fetch_dynamic(url)
                # 재시도할 때도 정제는 필수!
                clean_text = get_ai_friendly_html(list_html)
                notices = parse_with_ai(clean_text, url, user_profile)
            else:
                # 이미 동적인데 0건이면 토스처럼 HTML이 너무 길어서 AI가 길을 잃은 것
                LOG.warning(f"🔍 동적 분석도 0건 -> 더 강력하게 정제 후 마지막 재시도")
                # 팁: 아예 텍스트만 뽑아서 다시 시도
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(list_html, "html.parser")
                just_text = soup.get_text(separator="\n", strip=True)[:15000]
                notices = parse_with_ai(just_text, url, user_profile)

        LOG.info(f"🔍 최종 분석 결과: {len(notices)}건 발견")
        if not notices:
            if not is_dynamic_used:
                LOG.warning(f"🔍 1차(정적) 분석 0건 -> 2차(동적) 재시도 수행")
                list_html = await fetch_dynamic(url)
                notices = parse_with_ai(list_html, url, user_profile)
            else:
                # 이미 동적 크롤링을 했는데도 0건이라면? 
                # 이건 'HTML 정제'가 부족해서 AI가 길을 잃었을 확률이 커.
                LOG.warning(f"🔍 동적 분석도 0건 -> HTML 정제 후 마지막 재시도")
                clean_html = get_ai_friendly_html(list_html) # 스크립트, 스타일 태그 제거
                notices = parse_with_ai(clean_html, url, user_profile)
                LOG.info(f"{clean_html}")

        LOG.info(f"🔍 최종 분석 결과: {len(notices)}건 발견")        
        seen_links = set()

        for n in notices:
            title = n.get("title", "제목 없음").strip()
            score = float(n.get("score", 0.0))
            raw_link = str(n.get("link") or "").strip()
            raw_date = n.get("date", "")

            # 1. 필수 데이터 검증 및 중복 체크
            if not raw_link or raw_link == "NULL" or raw_link in seen_links:
                continue
            seen_links.add(raw_link)

            # 2. 주소 조립 (연오가 짠 훌륭한 로직 활용)
            if raw_link.startswith("http"):
                full_link = raw_link
            elif raw_link.isdigit():
                if "sogang.ac.kr" in url:
                    full_link = f"https://sogang.ac.kr/ko/detail/{raw_link}?bbsConfigFk=2&namepage=AcademicNotice"
                else:
                    full_link = urljoin(url, raw_link)
            else:
                full_link = urljoin(url, raw_link)

            LOG.info(f"🔗 [DEBUG] 최종 결합 주소: {full_link}")

            # 3. 날짜 필터링 (안전한 버전)
            try:
                # 숫자와 대시만 남기기
                clean_date_str = re.sub(r"[^\d-]", "-", raw_date.replace(".", "-"))
                # "2024-05-20" 형태 추출
                match = re.search(r"(\d{4}-\d{2}-\d{2})", clean_date_str)
                if match:
                    post_date = datetime.strptime(match.group(1), "%Y-%m-%d").date()
                    if post_date < cutoff_date:
                        LOG.info(f"⏩ [SKIP] 기간 만료 ({post_date}): {title}")
                        continue
            except Exception:
                LOG.warning(f"⚠️ 날짜 파싱 건너뜀 (형식 미지원): {title}")
                # 날짜를 몰라도 중요도(score)가 높으면 일단 수집하도록 진행
            # [STEP 3] 적합도 통과 시 2차 정밀 수집 (DEEP_CRAWL)
            if score >= 0.5:
                LOG.info(f"🔍 [DEEP_CRAWL] 본문 진입: {full_link}")

                detail_html = fetch_static(full_link)
                # 상세 페이지도 정적 실패 시 동적 시도
                if not detail_html or len(detail_html) < 800:
                    detail_html = await fetch_dynamic(full_link)

                if detail_html:
                    # 마크다운 변환하여 저장
                    full_content = md(detail_html, strip=['script', 'style', 'nav', 'footer'])
                    
                    all_notices.append({
                        "title": title,
                        "originalUrl": full_link,
                        "fullContent": full_content[:2000],
                        "relevanceScore": score,
                        "timestamp": datetime.now(TIMEZONE).isoformat()
                    })
                    LOG.info(f"   ㄴ ✅ 수집 성공: {title}")

    return {"status": "SUCCESS", "count": len(all_notices), "data": all_notices}