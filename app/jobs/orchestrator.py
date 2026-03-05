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
    
    # [STEP 0] DB에서 '근본 타이틀' 매핑 정보 로드
    from app.database.supabase_client import supabase
    url_to_title_map = {}
    try:
        # recommendation 테이블의 url과 title을 가져옴 (url이 일치하는 기준)
        res = supabase.table("recommendation").select("url, title").execute()
        # { "https://toss.im/...": "토스", "https://sogang...": "서강대학교" }
        url_to_title_map = {row['url']: row['title'] for row in res.data if row.get('title')}
        LOG.info(f"📚 근본 타이틀 매핑 완료: {len(url_to_title_map)}건")
    except Exception as e:
        LOG.error(f"❌ 매핑 데이터 로드 실패: {e}")

    # [확장성] 사이트별 주소 조립 패턴
    SITE_PATTERNS = {
        "sogang.ac.kr": "https://sogang.ac.kr/ko/detail/{id}?bbsConfigFk=2&namepage=AcademicNotice",
        "ewha.ac.kr": "{base_path}?mode=view&articleNo={id}",
        "toss.im": "https://toss.im/career/job-detail?job_id={id}"
    }

    for url in target_urls:
        if not url: continue
        
        # [추가] target_urls 테이블의 타이틀 동기화
        current_site_name = url_to_title_map.get(url, "알림")
        try:
            # target_urls의 title이 비어있을 수 있으니 근본 값으로 업데이트 시도
            supabase.table("target_urls").update({"title": current_site_name}).eq("target_url", url).execute()
        except Exception as e:
            LOG.warning(f"⚠️ target_urls 타이틀 동기화 실패: {e}")

        # [STEP 1] 목록 수집 (정적 -> 부실하면 동적)
        LOG.info(f"⚡ [STEP 1] 목록 수집 시도: {url} ({current_site_name})")
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
        clean_text = get_ai_friendly_html(list_html, mode="list")
        LOG.info(f"🧹 텍스트 정제 완료 (글자수: {len(clean_text)})")
        
        notices = parse_with_ai(clean_text, url, user_profile)

        # 🚨 [재시도 로직] 결과가 0건일 때만 수행
        if not notices:
            if not is_dynamic_used:
                LOG.warning(f"🔍 1차(정적) 분석 0건 -> 2차(동적) 재시도 수행")
                list_html = await fetch_dynamic(url)
                clean_text = get_ai_friendly_html(list_html, mode="list")
                notices = parse_with_ai(clean_text, url, user_profile)
            else:
                LOG.warning(f"🔍 동적 분석도 0건 -> 텍스트 강제 추출 후 마지막 재시도")
                from bs4 import BeautifulSoup

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

           # [STEP 3] DEEP_CRAWL 및 요약 로직
            if score >= 0.5:
                LOG.info(f"🔍 [DEEP_CRAWL] 진입: {full_link}")
                detail_html = None
                detail_html = fetch_static(full_link)
                if not detail_html or len(detail_html) < 800:
                    detail_html = await fetch_dynamic(full_link)
                

                # orchestrator.py 내부 수정 제안
                # [STEP 3] DEEP_CRAWL 내부에서 호출할 때
                if detail_html:
                    # 1. 일단 상세 모드로 시도
                    clean_detail = get_ai_friendly_html(detail_html, mode="detail")
                    
                    # 2. 🚨 [강력 처방] 200자도 안 된다? 이건 정제기가 범인임.
                    if len(clean_detail) < 200:
                        LOG.warning(f"⚠️ 정제 후 텍스트가 너무 짧음({len(clean_detail)}자). 원본 추출로 전환.")
                        from bs4 import BeautifulSoup
                        soup = BeautifulSoup(detail_html, "html.parser")
                        
                        # 스크립트랑 스타일만 지우고 싹 다 가져와!
                        for s in soup(["script", "style", "nav", "footer", "header"]):
                            s.decompose()
                            
                        # article 태그가 있으면 거기서만, 없으면 body 전체에서 텍스트 추출
                        main_body = soup.find("article") or soup.find("body") or soup
                        clean_detail = main_body.get_text(separator="\n", strip=True)

                    # 3. 마크다운 변환
                    full_content = md(clean_detail, strip=['script', 'style', 'nav', 'footer'])
    
    # 🚨 [추가 필터] 최종 결과가 너무 짧으면 수집 실패로 간주하고 다음 공고로!
                    if len(full_content) < 150:
                        LOG.error(f"❌ [COLLECT_FAIL] 본문 내용이 너무 부실함({len(full_content)}자). 건너뜁니다.")
                        continue               # 🚨 로그 괄호 제거해서 튜플 출력 방지
                    LOG.info(f"📝 본문 추출 완료 (글자수: {len(full_content)})")
                    
                    # AI 요약 생성 (아까 만든 함수 호출)
                    try:
                        from app.parser.ai_parser import summarize_content
                        summary_text = summarize_content(full_content, user_profile)
                    except Exception as e:
                        LOG.warning(f"⚠️ 요약 실패: {e}")
                        summary_text = full_content[:150].strip() + "..."

                    all_notices.append({
                        "title": title,
                        "source_name": current_site_name,
                        "originalUrl": full_link,
                        "fullContent": full_content[:3000], 
                        "summary": summary_text,           # 👈 드디어 요약본이 들어감!
                        "is_sent": False,
                        "timestamp": datetime.now(TIMEZONE).isoformat()
                    })
                    LOG.info(f"✅ [COLLECTED] {title}")

    return {"status": "SUCCESS", "count": len(all_notices), "data": all_notices}