import os

import requests
import uvicorn
import json
from fastapi import FastAPI
import logging
import traceback
from datetime import datetime, timedelta

from fastapi import FastAPI, Request
from pydantic import BaseModel, Field
from typing import List, Optional

# 크롤링 로직 임포트
from supabase import create_client, Client
from app.jobs.korea_university import run 
from typing import Any

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
    userId: str
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

# --- 엔드포인트 1: 크롤링 요청 ---
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
            # 이제 KeyError 없이 잘 읽힐 거야!
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
                "created_at": item.get("timestamp") 
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
    now = datetime.now()
    # 30분 단위 스케줄러이므로 초는 00으로 고정해서 비교
    current_time = now.strftime("%H:%M:00") 
    
    try:
        # 1. 지금 알림이 필요한 유저들만 조회
        user_res = supabase.table("users").select("*").eq("alarm_time", current_time).execute()
        target_users = user_res.data

        for user in target_users:
            sent_count = 0

            # 1. 주기 체크 (생략 - 기존 로직 유지)

            # 2. 이 유저에게 쌓인 안 보낸 공지들 가져오기
            noti_res = supabase.table("notifications") \
                .select("*") \
                .eq("user_id", user["user_id"]) \
                .eq("is_sent", False).execute()
            
            notis = noti_res.data
            if not notis: continue

            # 🔥 [수겸님 가이드 반영] 공지마다 카톡을 따로 전송
            for noti in notis:
                # 3. 수겸님이 정해준 양식(Parameter)에 정확히 맞추기
                params = {
                    "korean-title": noti['title'],     # 제목
                    "customer-name": user['username'], # 이름
                    "article-link": noti['original_url'] # 링크
                }

                # 4. 발송
                clean_phone = user['phone_number'].replace("-", "")
                api_resp = send_kakao(clean_phone, "send-article", params)

                # 5. 발송 성공 시 해당 공지만 '보냄' 처리
                if "error" not in api_resp:
                    supabase.table("notifications") \
                        .update({"is_sent": True}) \
                        .eq("id", noti["id"]).execute()
                    sent_count += 1
            
            # 유저별 발송 완료 후 전송 시점 기록
            supabase.table("users").update({"last_sent_at": now.isoformat()}).eq("user_id", user["user_id"]).execute()
            return {"status": "SUCCESS", "total_sent": sent_count}

    except Exception as e:
        LOG.error(f"💥 스케줄러 실행 에러: {e}")
    

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
        LOG.info(f"Kakao API 응답 상태: {resp.status_code}")
        
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
async def handle_crawl_dispatch():
    now = datetime.now()
    # 30분 단위 스케줄러 비교 (초는 00으로 고정)
    current_time = now.strftime("%H:%M:00")
    
    try:
        # 1. 지금이 알람 시점인 유저들 찾기
        user_res = supabase.table("users").select("*").eq("alarm_time", current_time).execute()
        target_users = user_res.data

        if not target_users:
            return {"status": "SUCCESS", "message": "이 시간에 예약된 크롤링 작업이 없습니다."}

        processed_count = 0

        for user in target_users:
            # 2. interval_days 기반 주기 체크
            # notifications 테이블에서 해당 유저의 가장 최신 공지 생성일 조회
            last_noti = supabase.table("notifications") \
                .select("created_at") \
                .eq("user_id", user["user_id"]) \
                .order("created_at", desc=True) \
                .limit(1).execute()

            should_run = False
            if not last_noti.data:
                should_run = True # 데이터가 아예 없으면 첫 크롤링 실행
            else:
                # DB의 timestamp string을 datetime 객체로 변환
                last_dt = datetime.fromisoformat(last_noti.data[0]["created_at"].replace('Z', '+00:00'))
                days_diff = (now.date() - last_dt.date()).days
                if days_diff >= user["interval_days"]:
                    should_run = True

            if should_run:
                # 3. 해당 유저의 모든 target_url 가져오기
                url_res = supabase.table("target_urls") \
                    .select("target_url") \
                    .eq("user_id", user["user_id"]).execute()
                
                urls = [item["target_url"] for item in url_res.data]
                
                if urls:
                    # 4. 크롤러(run 함수) 실행을 위한 이벤트 구성
                    event = {
                        "userId": user["user_id"],
                        "targetUrls": urls,
                        "userProfile": {
                            "username": user["username"],
                            "major": user["major"],
                            "school": user["school"],
                            # AI가 참고할 정보들
                            "intervalDays": user["interval_days"]
                        },
                        "callbackUrl": f"{os.getenv('BASE_URL')}/callback/save"
                    }
                    
                    # 크롤러 실행!
                    run(event)
                    processed_count += 1

        return {
            "status": "SUCCESS", 
            "triggered_user_count": processed_count,
            "time": current_time
        }

    except Exception as e:
        LOG.error(f"💥 디스패처 실행 에러: {traceback.format_exc()}")
        return {"status": "ERROR", "message": str(e)}
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run("app.main:app", host="0.0.0.0", port=port, reload=True)