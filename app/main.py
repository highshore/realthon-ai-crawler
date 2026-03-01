import asyncio
import sys
import os
import logging
import traceback
import requests
import json
from datetime import datetime
from typing import Any, List, Optional
from pydantic import BaseModel, Field

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from supabase import create_client, Client

# [1. 최상단 고정] Windows에서 Playwright 브라우저 실행을 위한 루프 정책 설정
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

# [2. 내부 모듈 임포트] 루프 정책 설정 후에 진행
from app.jobs.orchestrator import run, TIMEZONE
from app.utils.helpers import guess_site_name

# 로깅 및 세션 설정
logging.basicConfig(level=logging.INFO)
LOG = logging.getLogger(__name__)
session = requests.Session()
HTTP_TIMEOUT = 30

# [3. 환경 변수 설정]
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
SENDER_KEY = os.getenv("KAKAO_SENDER_KEY")
SECRET_KEY = os.getenv("KAKAO_SECRET_KEY")
APP_KEY = os.getenv("KAKAO_APP_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

app = FastAPI(
    title="Notice Alarm Service",
    servers=[{"url": "http://localhost:8080", "description": "로컬 테스트용"}],
    root_path=""
)

# [4. CORS 미들웨어]
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- 모델 정의 ---
class CallbackData(BaseModel):
    userId: Any
    data: List[dict]

class UserProfile(BaseModel):
    username: str
    phoneNumber: str

class CallbackConfig(BaseModel):
    enabled: bool = True
    callbackUrl: str
    authToken: str

class BatchRequest(BaseModel):         
    targetUrls: List[str]
    userId: int
    userProfile: UserProfile
    summary: str
    callback: CallbackConfig

# --- 내부 함수: 카카오 알림톡 발송 ---
def send_kakao(contact: str, template_code: str, template_param: dict[str, str]) -> dict[str, Any]:
    payload = {
        "senderKey": SENDER_KEY,
        "templateCode": template_code,
        "recipientList": [{"recipientNo": contact, "templateParameter": template_param}],
    }
    headers = {
        "X-Secret-Key": SECRET_KEY, 
        "Content-Type": "application/json;charset=UTF-8"
    }
    url = f"https://api-alimtalk.cloud.toast.com/alimtalk/v2.2/appkeys/{APP_KEY}/messages"
    
    try:
        resp = session.post(url, json=payload, headers=headers, timeout=HTTP_TIMEOUT)
        result_json = resp.json()
        LOG.info(f"📡 Kakao API Response: {json.dumps(result_json, ensure_ascii=False)}")
        return result_json
    except Exception as e:
        LOG.error(f"❌ Kakao API Error: {e}")
        return {"error": "CONNECTION_ERROR", "message": str(e)}

# --- 내부 함수: 콜백 데이터 전송 ---
def send_to_callback_list(callback_url: str, notices: List[dict], auth_token: str, user_id: int):
    scores = [float(item.get("relevanceScore", 0.0)) for item in notices]
    top_score = round(max(scores), 2) if scores else 0.0

    payload = {
        "userId": str(user_id),
        "relevanceScore": top_score,
        "data": notices
    }
    headers = {"Content-Type": "application/json", "X-AI-CALLBACK-TOKEN": auth_token}
    
    try:
        resp = requests.post(callback_url, json=payload, headers=headers, timeout=HTTP_TIMEOUT)
        LOG.info(f"📡 콜백 전송 완료 (상태코드: {resp.status_code})")
    except Exception as e:
        LOG.error(f"❌ 콜백 전송 실패: {e}")

# --- 엔드포인트: 크롤링 실행 디스패처 ---
@app.post("/scheduler/dispatch-crawl")
async def handle_crawl_dispatch():
    try:
        user_res = supabase.table("users").select("*").execute() 
        target_users = user_res.data
        LOG.info(f"🚀 디스패처 시작 - 대상 유저: {len(target_users)}명")

        processed_count = 0
        base_url = os.getenv("BASE_URL", "http://localhost:8080").rstrip("/")

        for user in target_users:
            url_res = supabase.table("target_urls").select("target_url").eq("user_id", user["user_id"]).execute()
            urls = [item["target_url"] for item in url_res.data]
            
            for url in urls:
                site_name = guess_site_name(url)
                crawl_event = {
                    "userId": user["user_id"],
                    "targetUrls": [url],
                    "siteName": site_name,
                    "userProfile": {"username": user.get("username")},
                    "callbackUrl": f"{base_url}/callback/save"
                }

                LOG.info(f"📡 [DISPATCH] {user.get('username')}님 - {site_name} 시작")
                result = await run(crawl_event) 
                
                if result.get("status") == "SUCCESS" and result.get("data"):
                    send_to_callback_list(
                        callback_url=crawl_event["callbackUrl"],
                        notices=result["data"],
                        auth_token="X-AI-CALLBACK-TOKEN",
                        user_id=user["user_id"]
                    )
            processed_count += 1
        return {"status": "SUCCESS", "processed_users": processed_count}
    except Exception as e:
        LOG.error(f"💥 디스패처 에러: {traceback.format_exc()}")
        return {"status": "ERROR", "message": str(e)}

# ... (상단 import 및 루프 정책 설정 코드는 그대로 유지) ...

# --- 엔드포인트: 데이터 저장 (에러 수정 버전) ---
@app.post("/callback/save")
async def handle_crawler_result(payload: CallbackData):
    LOG.info(f"📥 [SAVE] 콜백 수신! 데이터 개수: {len(payload.data)}")
    try:
        user_id = payload.userId
        # payload.data가 NoticeItem 객체 리스트로 들어오기 때문에 접근 방식을 바꿉니다.
        data_list = payload.data 

        # 중복 체크
        existing_res = supabase.table("notifications").select("original_url").eq("user_id", int(user_id)).execute()
        existing_urls = {item['original_url'] for item in existing_res.data}

        insert_data = []
        for item in data_list:
            # 💡 [핵심 수정] Pydantic 모델 객체이므로 getattr을 쓰거나 점(.)으로 접근해야 합니다.
            # 객체일 경우를 대비해 getattr을 쓰고, 혹시 dict일 경우를 대비해 .get을 보조로 씁니다.
            def get_val(obj, key, default=None):
                if hasattr(obj, 'get'): # dict인 경우
                    return obj.get(key, default)
                return getattr(obj, key, default) # 객체인 경우

            url = get_val(item, "originalUrl") or get_val(item, "original_url")
            
            if not url or url in existing_urls:
                continue

            insert_data.append({
                "user_id": int(user_id),
                "title": get_val(item, "title", "제목 없음"),
                "summary": get_val(item, "summary", "요약 없음"),
                "source_name": get_val(item, "sourceName", "지능형 크롤러"),
                "original_url": url,
                "category": get_val(item, "category", "일반"),
                "is_liked": True,
                "is_sent": False, # ✅ 발송 전 상태 기본값
                "notice_date": datetime.now(TIMEZONE).isoformat(),
            })

        if insert_data:
            supabase.table("notifications").insert(insert_data).execute()
            LOG.info(f"✅ {user_id}번 유저 신규 {len(insert_data)}건 저장 완료")
        
        return {"status": "SUCCESS"}
    except Exception as e:
        LOG.error(f"❌ 저장 에러 상세: {traceback.format_exc()}")
        return {"status": "ERROR", "message": str(e)}

# --- 실행부 (루프 강제 지정 방식) ---
# --- 엔드포인트: 알림 발송 스케줄러 ---
@app.post("/scheduler/send-notifications")
async def handle_notification_scheduler():
    now = datetime.now(TIMEZONE)
    current_hour = now.replace(minute=0, second=0, microsecond=0).strftime("%H:%M:%S")
    LOG.info(f"⏰ 알림 스케줄러 가동 (시간: {current_hour})")
    
    try:
        target_users = supabase.table("users").select("*").eq("alarm_time", current_hour).execute().data
        if not target_users: return {"status": "SUCCESS", "message": "No users for this hour."}

        sent_count = 0
        for user in target_users:
            notis = supabase.table("notifications").select("*").eq("user_id", user["user_id"]).eq("is_sent", False).execute().data
            if not notis: continue

            titles = [f"• {n['title']}" for n in notis[:5]]
            combined = "\n".join(titles) + (f"\n외 {len(notis)-5}건 더 있음" if len(notis)>5 else "")

            params = {"korean-title": combined, "customer-name": user['username'], "article-link": notis[0]['original_url']}
            api_resp = send_kakao(user['phone_number'].replace("-", ""), "send-article", params)

            if "error" not in api_resp:
                supabase.table("notifications").update({"is_sent": True}).eq("user_id", user["user_id"]).execute()
                sent_count += 1
        return {"status": "SUCCESS", "sent_user_count": sent_count}
    except Exception as e:
        LOG.error(f"💥 발송 에러: {traceback.format_exc()}")
        return {"status": "ERROR", "message": str(e)}

# --- 에러 핸들러 및 실행 ---
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(status_code=422, content={"detail": exc.errors()})
if __name__ == "__main__":
    import uvicorn
    # 💡 Windows에서 NotImplementedError를 방지하기 위해 loop='asyncio'를 명시합니다.
    # 또한 포트가 8080인지 다시 한번 확인하세요.
    uvicorn.run("app.main:app", host="0.0.0.0", port=8080, reload=True, loop="asyncio")
