import os
#from fastapi import BackgroundTasks # 👈 상단에 추가
import requests
import uvicorn
import json
from fastapi import FastAPI
import logging
import traceback
from datetime import datetime, timedelta
from typing import Any # 상단에 추가되어 있는지 확인
from fastapi import FastAPI, Request
from pydantic import BaseModel, Field
from typing import List, Optional

# 크롤링 로직 임포트
from supabase import create_client, Client
from app.jobs.korea_university import TIMEZONE
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from app.jobs.orchestrator import run  # 이렇게 경로만 바꿔줍니다.
# 로깅 설정 (없다면 추가)
LOG = logging.getLogger(__name__)
# 세션 설정 (없다면 추가, 성능을 위해 세션을 재사용하는 게 좋아)
session = requests.Session()

# 타임아웃 설정 (초 단위)
HTTP_TIMEOUT = 10

# [필수] Supabase 설정 (환경변수에서 읽기)
SENDER_KEY = os.getenv("KAKAO_SENDER_KEY")
SECRET_KEY = os.getenv("KAKAO_SECRET_KEY")
APP_KEY = os.getenv("KAKAO_APP_KEY")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# 라우터 임포트 (batch_manager.py에 router = APIRouter()가 있어야 함)
#from app.batch_manager import router as batch_router

app = FastAPI()

#if batch_router:
#    app.include_router(batch_router)

# --- 모델 정의 (생략 없이 유지) ---
class CallbackData(BaseModel):
    userId: Any
    data: List[dict]
class UserProfile(BaseModel):
    username: str
    phoneNumber: str
class CallbackConfig(BaseModel):
    enabled: bool = True         # 👈 추가
    callbackUrl: str      # 👈 추가
    authToken: str
class BatchRequest(BaseModel):         
    targetUrls: List[str]  # targetUrl(str)에서 targetUrls(List[str])로 변경!
    userId: int
    userProfile: UserProfile
    summary: str
    callback: CallbackConfig

# --- 엔드포인트 1: 크롤링 요청 --- 지금은 안씀 그냥 남겨둚.
@app.post("/crawl/request")
async def handle_crawl(request_data: BatchRequest):
    try:
        # Pydantic 모델을 딕셔너리로 변환
        data_dict = request_data.model_dump()
        
        # 🔴 [주의] 여기서 data_dict["callback"]은 CallbackConfig의 내용을 담은 dict임
        event = {
            "userId": data_dict["userId"],
            "targetUrls": data_dict["targetUrls"],
            "userProfile": data_dict["userProfile"],
            "callbackUrl": data_dict["callback"]["callbackUrl"] 
        }

        # [수정 2] 로그 찍을 때도 리스트 전체를 보여주거나 첫 번째 걸 찍어야 함
        print(f"DEBUG: 크롤링 시작 (URLs: {data_dict['targetUrls']})")
        print(f"📡 DEBUG: 크롤링 프로세스 시작 (UserId: {event['userId']})")

        # 이제 run(event) 내부에서 targetUrls 리스트를 돌며 크롤링함
        # ⚠️ 중요: run 함수가 동기 함수라면 스레드 풀에서 실행하는게 좋지만 우선 유지
        result = run(event)

        if not result or result.get("status") != "SUCCESS":
            msg = result.get("message") if result else "결과 없음"
            print(f"⚠️ 건너뜀: {msg}")
            return {"status": "SKIPPED", "message": msg}

        # [데이터 전송] 
        if data_dict["callback"].get("enabled"): 
            actual_notices = result.get("data", [])            
            if actual_notices:
                # 여기서 은서님 서버로 데이터 쏨
                send_to_callback_list(
                    data_dict["callback"]["callbackUrl"],
                    actual_notices,
                    data_dict["callback"]["authToken"],
                    data_dict["userId"] # userId 추가 전달
                )
            else:
                print("⚠️ 적합한 공지가 없어 콜백을 생략합니다.")
            
        
        return {"status": "SUCCESS", "count": len(result.get("data", []))}

    except Exception as e:
        print(f"💥 서버 에러: {str(e)}")
        import traceback
        print(traceback.format_exc()) # 에러 위치 정확히 보려고 추가
        print(f"💥 크롤링 요청 처리 중 에러: {traceback.format_exc()}")
        return {"status": "ERROR", "message": str(e)}

# --- 엔드포인트 2: 콜백 데이터 저장 ---
@app.post("/callback/save")
async def handle_crawler_result(payload: CallbackData):
    print(f"📥 [SAVE] 콜백 수신 성공! 데이터 개수: {len(payload.data)}")
    try:
        user_id = payload.userId
        data_list = payload.data

        # 1. 현재 이 유저의 기존 공지 URL들을 가져옴 (중복 체크용)
        existing_res = supabase.table("notifications") \
            .select("original_url") \
            .eq("user_id", int(user_id)) \
            .execute()
        
        # 이미 DB에 있는 URL들을 set으로 만듦 (검색 속도 향상)
        existing_urls = {item['original_url'] for item in existing_res.data}

        insert_data = []
        for item in data_list:
            target_url = item.get("originalUrl")
            
            # 🔥 [핵심] 이미 DB에 있는 URL이라면 스킵!
            if target_url in existing_urls:
                continue

            insert_data.append({
                "user_id": int(user_id),
                "title": item.get("title"),
                "summary": item.get("summary"),
                "source_name": item.get("sourceName"),
                "original_url": target_url,
                "category": item.get("category"),
                "is_liked": True,
                "created_at": item.get("timestamp") ,
                "notice_date": datetime.now(TIMEZONE).isoformat(), # 전송/수집일 (오늘)
                "is_sent": False,
            })

        if insert_data:
            supabase.table("notifications").insert(insert_data).execute()
            print(f"✅ {user_id}번 유저 신규 데이터 {len(insert_data)}건 저장 완료")
        else:
            print(f"ℹ️ {user_id}번 유저: 새로 추가할 신규 공지가 없습니다.")

        return {"status": "SUCCESS"}
        
    except Exception as e:
        print(f"💥 저장 실패: {str(e)}")
        return {"status": "ERROR", "message": str(e)}
        
def send_to_callback_list(callback_url: str, notices: List[dict], auth_token: str, user_id: int):
    scores = [float(item.get("relevanceScore", 0.0)) for item in notices]
    top_score = round(max(scores), 2) if scores else 0.0

    # 콜백 페이로드 준비
    payload = {
        "status": "SUCCESS",
        "userId": str(user_id), # 저장할 때 필요한 userId 포함
        "relevanceScore": top_score,
        "data": notices
    }

    # (선택) 디버그 출력
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    headers = {"Content-Type": "application/json", "X-AI-CALLBACK-TOKEN": auth_token}

    headers = {
        "Content-Type": "application/json",
        "X-AI-CALLBACK-TOKEN": auth_token
    }

    # 실제 콜백 전송
    try:
        response = requests.post(callback_url, json=payload, headers=headers, timeout=60)
        print(f"📡 콜백0 응답 코드: {response.status_code}")
        # 타임아웃 넉넉히 설정
        response = requests.post(callback_url, json=payload, headers=headers, timeout=30)
        print(f"📡 콜백 전송 완료 (상태코드: {response.status_code})")
    except Exception as e:
        print(f"❌ 콜백 전송 실패: {e}")
@app.post("/scheduler/send-notifications")
async def handle_notification_scheduler():
    now = datetime.now(TIMEZONE)
    current_hour_start = now.replace(minute=0, second=0, microsecond=0).strftime("%H:%M:%S")
    
    LOG.info(f"⏰ 알림 발송 스케줄러 가동 중... (대상 시간대: {current_hour_start})")
    
    try:
        user_res = supabase.table("users") \
            .select("*") \
            .eq("alarm_time", current_hour_start) \
            .execute()
        
        target_users = user_res.data
        if not target_users:
            LOG.info(f"ℹ️ {current_hour_start} 시간대에 설정된 알람이 없습니다.")
            return {"status": "SUCCESS", "message": "No target users for this hour."}

        total_sent_all_users = 0

        for user in target_users:
            # 1. 해당 유저의 미발송 공지 조회
            noti_res = supabase.table("notifications") \
                .select("*") \
                .eq("user_id", user["user_id"]) \
                .eq("is_sent", False).execute()
            
            notis = noti_res.data
            if not notis: 
                LOG.info(f"ℹ️ {user['username']}님: 보낼 새 공지가 없습니다.")
                continue

            # 2. 제목 묶기 (최대 5개)
            titles = [f"• {n['title']}" for n in notis[:5]]
            combined_titles = "\n".join(titles)
            if len(notis) > 5:
                combined_titles += f"\n외 {len(notis) - 5}건이 더 있습니다."

            # 3. 알림톡 파라미터 구성
            params = {
                "korean-title": combined_titles,
                "customer-name": user['username'],
                "article-link": notis[0]['original_url'] # 가장 최근 공지 링크
            }

            # 4. 실제 카카오톡 발송
            clean_phone = user['phone_number'].replace("-", "")
            api_resp = send_kakao(clean_phone, "send-article", params)

            # 5. 발송 성공 시 DB 업데이트
            # API 응답에 에러가 없고, 응답 코드가 성공(일반적으로 "S" 또는 resultCode 0)인지 확인
            if "error" not in api_resp:
                noti_ids = [n["user_id"] for n in notis]
                # Supabase 업데이트 실행
                update_res = supabase.table("notifications") \
                    .update({"is_sent": True}) \
                    .in_("user_id", noti_ids).execute()
                
                total_sent_all_users += 1 
                LOG.info(f"✅ {user['username']}님께 공지 {len(notis)}건 묶음 발송 완료")
            else:
                LOG.error(f"❌ {user['username']}님 발송 실패: {api_resp}")

        # 모든 유저 처리가 끝난 후 최종 결과 반환
        return {"status": "SUCCESS", "total_sent_user_count": total_sent_all_users}

    except Exception as e:
        # traceback을 통해 정확한 에러 위치 파악
        error_msg = traceback.format_exc()
        LOG.error(f"💥 스케줄러 실행 에러: {error_msg}")
        return {"status": "ERROR", "message": str(e)}
def send_kakao(contact: str, template_code: str, template_param: dict[str, str]) -> dict[str, Any]:
    # 🔴 주의: SENDER_KEY, SECRET_KEY, APP_KEY는 os.getenv 등으로 가져온 상태여야 함!
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
        # POST 요청 전송
        resp = session.post(url, json=payload, headers=headers, timeout=HTTP_TIMEOUT)
        
        # 로그 기록
        result_json = resp.json()
        LOG.info(f"📡 Kakao API Response Detail: {json.dumps(result_json, ensure_ascii=False)}")        
        if resp.status_code != 200:
            LOG.error(f"Kakao send failed ({resp.status_code}) {resp.text}")
            return {"error": "API_STATUS_ERROR", "status": resp.status_code, "detail": resp.text}
            
        # 정상 응답 반환
        return resp.json()
        
    except Exception as e:
        LOG.error(f"Kakao connection error: {e}")
        return {"error": "CONNECTION_ERROR", "message": str(e)}
    pass
    
@app.post("/scheduler/dispatch-crawl")
async def handle_crawl_dispatch(): # BackgroundTasks 제거
    try:
        user_res = supabase.table("users").select("*").execute() 
        target_users = user_res.data
        LOG.info(f"🚀 디스패처 시작 - 대상 유저: {len(target_users)}명")

        processed_count = 0
        for user in target_users:
            url_res = supabase.table("target_urls").select("target_url").eq("user_id", user["user_id"]).execute()
            urls = [item["target_url"] for item in url_res.data]
            
            if urls:
                # handle_crawl_dispatch 함수 내부 루프 안쪽
                crawl_event = {
                    "userId": user["user_id"],
                    "targetUrls": urls,
                    "userProfile": {
                        "username": user.get("username"),
                        "major": user.get("major"),
                        "school": user.get("school"),
                        "intervalDays": user.get("interval_days", 7)
                    },
                    "callbackUrl": f"{os.getenv('BASE_URL').rstrip('/')}/callback/save"
                }

                # 보낼 주소 로그를 명확히 찍어
                LOG.info(f"📡 [DISPATCH] {user.get('username')}님 크롤링 시작 요청")
                LOG.info(f"🔗 [DISPATCH] Callback URL 확인: {crawl_event['callbackUrl']}")

                result = run(crawl_event)
                processed_count += 1
                if result.get("status") == "SUCCESS" and result.get("data"):
        # 아까 정의해둔 콜백 전송 함수를 여기서 써야 해!
                    send_to_callback_list(
                        callback_url=crawl_event["callbackUrl"],
                        notices=result["data"],
                        auth_token="X-AI-CALLBACK-TOKEN", # 필요한 경우
                        user_id=user["user_id"]
                    )
                    LOG.info(f"✅ {user.get('username')}님 데이터를 저장소로 전송했습니다.")
                LOG.info(f"✅ {user.get('username')}님 크롤링 및 저장 프로세스 완료")

        return {"status": "SUCCESS", "message": f"{processed_count}명의 처리를 완료했습니다."}

    except Exception as e:
        LOG.error(f"💥 디스패처 에러: {traceback.format_exc()}")
        return {"status": "ERROR", "message": str(e)}
    

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    body = await request.body()
    # 어떤 필드 형식이 틀렸는지, 실제로 들어온 JSON이 뭔지 상세히 출력해
    LOG.error(f"❌ [422 Error] 유효성 검사 실패: {exc.errors()}")
    LOG.error(f"❌ [422 Error] 들어온 데이터 원본: {body.decode()}")
    return JSONResponse(
        status_code=422,
        content={"detail": exc.errors(), "body": body.decode()},
    )
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run("app.main:app", host="0.0.0.0", port=port, reload=True)