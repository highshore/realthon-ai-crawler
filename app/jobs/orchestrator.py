import logging
import requests
from datetime import datetime
from zoneinfo import ZoneInfo
from app.models import CallbackData
from app.engine.dynamic_fetcher import fetch_dynamic
from app.engine.static_fetcher import fetch_static
from app.parser.ai_parser import parse_with_ai

LOG = logging.getLogger(__name__)
TIMEZONE = ZoneInfo("Asia/Seoul")
RELEVANCE_THRESHOLD = 0.5  # AI가 반환하는 적합도 점수의 임계값 (0.0~1.0)
async def run(event):
    LOG.info("🚀 지능형 하이브리드 크롤링 프로세스 시작")
    request_site_name = event.get("siteName") or "알 수 없는 출처"
    target_urls = event.get("targetUrls") or [event.get("targetUrl")]
    user_profile = event.get("userProfile", {})
    user_id = event.get("userId")
    
    all_notices = []

    for url in target_urls:
        if not url: continue
        
        # 1. 동적 수집 시도 (Playwright)
        content = await fetch_dynamic(url)
        
        # 2. 실패 시 정적 수집 시도 (Requests)
        if not content or len(content) < 100:
            LOG.warning(f"⚠️ 동적 수집 실패, 정적으로 전환: {url}")
            content = fetch_static(url)

        if not content:
            LOG.error(f"❌ 모든 수집 수단 실패: {url}")
            continue

        # 3. AI 범용 파싱 (Gemini 2.0)
        # 3. AI 범용 파싱 (Gemini 2.0) - 여기서 목록과 링크를 먼저 추출함
        notices = parse_with_ai(content, url, user_profile)
        LOG.info(f"📍 [LIST_FETCH] URL: {url} | Found: {len(notices)}건")
        
        for n in notices:
            link = n.get("link") or n.get("url") or n.get("originalUrl") or n.get("original_url")
            title = n.get("title", "제목 없음")
            score = float(n.get("score", 0.0))
            score = float(n.get("score", 0.0))
    
            if score < RELEVANCE_THRESHOLD:
                LOG.info(f"⏩ [SKIP] 점수 미달 ({score}점): {title}")
                continue
                
            # 점수가 높을 때만 아래 로직 실행 (상세 페이지 방문 등)
            LOG.info(f"✅ [PASS] 적합 공지 발견 ({score}점): {title}")
            if not link:
                LOG.warning(f"⚠️ 링크가 없어 스킵: {title}")
                continue

            # -------------------------------------------------------
            # [핵심 추가] 2차 크롤링: 적합도가 높으면 상세 페이지로 진입
            # -------------------------------------------------------
            full_content = "상세 본문을 가져오지 못했습니다."
            if score >= 0.5:  # 임계값은 조절 가능
                LOG.info(f"🔍 [DEEP_CRAWL] 상세 페이지 진입 중: {title} ({link})")
                try:
                    # 상세 페이지는 내용이 중요하므로 다시 동적/정적 수집 시도
                    detail_html = await fetch_dynamic(link)
                    if not detail_html or len(detail_html) < 200:
                        detail_html = fetch_static(link)
                    
                    # 수집된 HTML에서 텍스트만 추출 (AI를 한 번 더 써서 요약하거나, 텍스트만 뽑기)
                    # 여기서는 간단하게 detail_html 자체를 넘기거나 텍스트 추출 로직 연결
                    full_content = detail_html  
                    
                    # 만약 상세 본문을 기반으로 '진짜 요약'을 다시 하고 싶다면:
                    # n["summary"] = await summarize_deep(detail_html, user_profile)
                except Exception as e:
                    LOG.error(f"❌ 상세 페이지 수집 실패 ({title}): {e}")

            all_notices.append({
                "title": title,
                "summary": n.get("summary") or "요약 없음",
                "originalUrl": str(link),
                "fullContent": full_content, # 👈 상세 본문 추가
                "sourceName": request_site_name,
                "relevanceScore": score,
                "timestamp": datetime.now(TIMEZONE).isoformat()
            })
            LOG.info(f"   ㄴ ✅ 수집 완료: {title} (점수: {score})")

    # 4. 결과 저장 처리
    payload_data = {
        "userId": str(user_id),
        "data": all_notices
    }

    # 5. 내부 직접 호출 시도 (데드락 방지 및 성능 최적화)

    return {
        "status": "SUCCESS", 
        "count": len(all_notices),
        "data": all_notices  # 👈 이 줄을 반드시 추가해!}
    }