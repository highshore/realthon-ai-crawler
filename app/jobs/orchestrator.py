import logging
import re
from datetime import datetime, timedelta
from urllib.parse import urljoin, urlparse
from markdownify import markdownify as md
from bs4 import BeautifulSoup

# [임포트 정리]
from app.utils.helpers import TIMEZONE, get_ai_friendly_html, is_valid_content
from app.engine.static_fetcher import fetch_static
from app.engine.dynamic_fetcher import fetch_dynamic
from app.parser.ai_parser import parse_with_ai

LOG = logging.getLogger(__name__)

async def run(event):
    user_profile = event.get("userProfile", {})
    target_urls = event.get("targetUrls") or [event.get("targetUrl")]
    interval_days = int(user_profile.get("intervalDays", 3))
    cutoff_date = (datetime.now(TIMEZONE) - timedelta(days=interval_days)).date()

    all_notices = []
    
    # [확장성] 사이트별 주소 조립 패턴
    SITE_PATTERNS = {
        "sogang.ac.kr": "https://sogang.ac.kr/ko/detail/{id}?bbsConfigFk=2&namepage=AcademicNotice",
        "ewha.ac.kr": "{base_path}?mode=view&articleNo={id}",
        "toss.im": "https://toss.im/career/job-detail?job_id={id}"
    }

    for url in target_urls:
        if not url: continue
        
        # [STEP 1] 목록 수집 (정적 -> 부실하면 동적)
        LOG.info(f"⚡ [STEP 1] 목록 수집 시도: {url}")
        list_html = fetch_static(url)
        is_dynamic_used = False

        if not list_html or not is_valid_content(list_html):
            LOG.warning(f"⚠️ 정적 데이터 부실. 즉시 동적(Dynamic) 전환.")
            list_html = await fetch_dynamic(url)
            is_dynamic_used = True

        if not list_html:
            LOG.error(f"❌ 목록 수집 실패: {url}")
            continue

        # [STEP 2] AI 분석 (정제된 텍스트 전달)
        clean_text = get_ai_friendly_html(list_html)
        LOG.info(f"🧹 텍스트 정제 완료 (글자수: {len(clean_text)})")
        
        notices = parse_with_ai(clean_text, url, user_profile)

        # 🚨 [재시도 로직] 결과가 0건일 때만 수행
        if not notices:
            if not is_dynamic_used:
                LOG.warning(f"🔍 1차(정적) 분석 0건 -> 2차(동적) 재시도 수행")
                list_html = await fetch_dynamic(url)
                clean_text = get_ai_friendly_html(list_html)
                notices = parse_with_ai(clean_text, url, user_profile)
            else:
                LOG.warning(f"🔍 동적 분석도 0건 -> 텍스트 강제 추출 후 마지막 재시도")
                soup = BeautifulSoup(list_html, "html.parser")
                just_text = soup.get_text(separator="\n", strip=True)[:15000]
                notices = parse_with_ai(just_text, url, user_profile)

        LOG.info(f"🔍 최종 분석 결과: {len(notices)}건 발견")
        
        seen_links = set()
        for n in notices:
            title = n.get("title", "제목 없음").strip()
            score = float(n.get("score", 0.0))
            raw_link = str(n.get("link") or n.get("id") or "").strip()
            raw_date = n.get("date", "")

            if not raw_link or raw_link == "NULL":
                continue
            
            # 주소 자동 조립
            full_link = None
            if raw_link.startswith("http"):
                full_link = raw_link
            else:
                domain = next((d for d in SITE_PATTERNS if d in url), None)
                if domain and raw_link.isdigit():
                    pattern = SITE_PATTERNS[domain]
                    base_path = url.split('?')[0]
                    full_link = pattern.format(id=raw_link, base_path=base_path)
                else:
                    full_link = urljoin(url, raw_link)

            if full_link in seen_links: continue
            seen_links.add(full_link)

            # 날짜 필터링
            try:
                clean_date_str = re.sub(r"[^\d-]", "-", raw_date.replace(".", "-"))
                match = re.search(r"(\d{4}-\d{2}-\d{2})", clean_date_str)
                if match:
                    post_date = datetime.strptime(match.group(1), "%Y-%m-%d").date()
                    if post_date < cutoff_date:
                        LOG.info(f"⏩ [SKIP] 기간 만료 ({post_date}): {title}")
                        continue
            except Exception:
                LOG.warning(f"⚠️ 날짜 파싱 건너뜀: {title}")

            # [STEP 3] DEEP_CRAWL
            if score >= 0.5:
                LOG.info(f"🔍 [DEEP_CRAWL] 진입: {full_link}")
                detail_html = fetch_static(full_link)
                if not detail_html or len(detail_html) < 800:
                    detail_html = await fetch_dynamic(full_link)

                if detail_html:
                    clean_detail = get_ai_friendly_html(detail_html)
                    full_content = md(clean_detail, strip=['script', 'style', 'nav', 'footer'])
                    
                    all_notices.append({
                        "title": title,
                        "originalUrl": full_link,
                        "fullContent": full_content[:2000],
                        "relevanceScore": score,
                        "is_sent": False,
                        "timestamp": datetime.now(TIMEZONE).isoformat()
                    })
                    LOG.info(f"✅ [COLLECTED] {title}")

    return {"status": "SUCCESS", "count": len(all_notices), "data": all_notices}