import logging
from datetime import datetime
from zoneinfo import ZoneInfo
from app.engine.dynamic_fetcher import fetch_dynamic
from app.engine.static_fetcher import fetch_static
from app.parser.ai_parser import parse_with_ai
from app.database.supabase_client import save_notifications

LOG = logging.getLogger(__name__)
TIMEZONE = ZoneInfo("Asia/Seoul")

def run(event):
    LOG.info("🚀 지능형 하이브리드 크롤링 프로세스 시작")
    
    target_urls = event.get("targetUrls") or [event.get("targetUrl")]
    user_profile = event.get("userProfile", {})
    user_id = event.get("userId")
    
    all_notices = []

    for url in target_urls:
        if not url: continue
        
        # 1. 동적 수집 시도 (Playwright)
        content = fetch_dynamic(url)
        
        # 2. 실패 시 정적 수집 시도 (Requests)
        if not content or len(content) < 100:
            LOG.warning(f"⚠️ 동적 수집 실패, 정적으로 전환: {url}")
            content = fetch_static(url)

        if not content:
            LOG.error(f"❌ 모든 수집 수단 실패: {url}")
            continue

        # 3. AI 범용 파싱 (Gemini 2.0)
        # 학교 구분 없이 AI가 문맥으로 공지사항을 추출합니다.
        notices = parse_with_ai(content, url, user_profile)
        
        for n in notices:
            all_notices.append({
                "user_id": user_id,
                "title": n.get("title"),
                "summary": n.get("summary"),
                "original_url": n.get("link"),
                "source_name": "지능형 크롤러",
                "relevance_score": n.get("score", 0.0),
                "timestamp": datetime.now(TIMEZONE).isoformat()
            })

    # 4. 결과 저장 (Optional: orchestrator에서 직접 저장하거나 main에 반환)
    return {
        "status": "SUCCESS",
        "count": len(all_notices),
        "data": all_notices
    }