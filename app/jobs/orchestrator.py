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
        notices = parse_with_ai(content, url, user_profile)
        
        for n in notices:
            # AI가 준 데이터에서 링크를 찾기 위해 여러 키를 시도합니다.
            link = n.get("link") or n.get("url") or n.get("originalUrl") or n.get("original_url")
            
            if not link:
                LOG.warning(f"⚠️ 공지사항에서 링크를 찾을 수 없어 스킵합니다: {n.get('title')}")
                continue

            all_notices.append({
                "title": n.get("title") or "제목 없음",
                "summary": n.get("summary") or "요약 없음",
                "originalUrl": str(link),  # 확실하게 문자열로 변환
                "sourceName": "지능형 크롤러",
                "category": n.get("category") or "일반",
                "sourceName": request_site_name,
                "relevanceScore": float(n.get("score", 0.0)),
                "timestamp": datetime.now(TIMEZONE).isoformat()
            })

    # 4. 결과 저장 처리
    payload_data = {
        "userId": str(user_id),
        "data": all_notices
    }

    # 5. 내부 직접 호출 시도 (데드락 방지 및 성능 최적화)
    try:
        from app.main import handle_crawler_result

        # 내부 함수 직접 호출 (await 사용)
        LOG.info(f"💾 내부 저장 로직 직접 호출 시도 (User: {user_id})")
        callback_obj = CallbackData(**payload_data)
        await handle_crawler_result(callback_obj)
        LOG.info("✅ 내부 저장 완료")
        
    except Exception as e:
        # 내부 호출 실패 시 Fallback: HTTP 요청 (기존 방식)
        LOG.warning(f"🔄 내부 호출 실패로 인한 HTTP 콜백 전환: {e}")
        callback_url = event.get("callbackUrl") or "http://localhost:8080/callback/save"
        try:
            response = requests.post(callback_url, json=payload_data, timeout=10)
            LOG.info(f"📡 HTTP 콜백 결과: {response.status_code}")
        except Exception as http_e:
            LOG.error(f"❌ 콜백 최종 실패: {http_e}")

    return {"status": "SUCCESS", "count": len(all_notices)}