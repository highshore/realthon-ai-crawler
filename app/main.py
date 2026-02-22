import os
import requests
import uvicorn
import json
import logging
import traceback
from datetime import datetime, timedelta

from fastapi import FastAPI, Request
from pydantic import BaseModel, Field
from typing import List, Optional
from supabase import create_client, Client
from app.jobs.korea_university import run 

# [필수] Supabase 설정 (환경변수에서 읽기)
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
    school: str
    major: str
    interestFields: List[str]
    intervalDays: int
    alarmTime: str

class CallbackConfig(BaseModel):
    enabled: bool = True
    callbackUrl: str = Field(default="https://api.allyeojujob.com/ai/callback")
    authToken: str

class BatchRequest(BaseModel):
    userId: int
    targetUrls: List[str]
    userProfile: UserProfile
    summary: str
    callback: CallbackConfig

# --- 엔드포인트 1: 크롤링 요청 ---
@app.post("/crawl/request")
async def handle_crawl(request_data: BatchRequest):
    try:
        data_dict = request_data.model_dump()
        event = {
            "userId": data_dict["userId"],
            "targetUrls": data_dict["targetUrls"],
            "userProfile": data_dict["userProfile"],
            "callbackUrl": data_dict["callback"]["callbackUrl"]
        }
        
        print(f"📡 DEBUG: 크롤링 프로세스 시작 (UserId: {event['userId']})")
        
        # ⚠️ 중요: run 함수가 동기 함수라면 스레드 풀에서 실행하는게 좋지만 우선 유지
        result = run(event)
        
        if not result or result.get("status") != "SUCCESS":
            return {"status": "SKIPPED", "message": result.get("message", "결과 없음")}

        if data_dict["callback"]["enabled"]:
            actual_notices = result.get("data", [])
            if actual_notices:
                send_to_callback_list(
                    data_dict["callback"]["callbackUrl"],
                    actual_notices,
                    data_dict["callback"]["authToken"],
                    data_dict["userId"] # userId 추가 전달
                )
        
        return {"status": "SUCCESS", "count": len(result.get("data", []))}
        
    except Exception as e:
        print(f"💥 크롤링 요청 처리 중 에러: {traceback.format_exc()}")
        return {"status": "ERROR", "message": str(e)}

# --- 엔드포인트 2: 콜백 데이터 저장 ---
@app.post("/callback/save")
async def handle_crawler_result(payload: CallbackData): # 규격(CallbackData) 적용됨
    try:
        # 🔴 [수정] payload는 이미 객체라서 .body()를 호출하면 안 돼!
        # 바로 데이터를 꺼내서 쓰면 됨
        user_id = payload.userId
        data_list = payload.data

        print(f"📩 {user_id}번 유저 알림 데이터 {len(data_list)}건 수신")

        insert_data = []
        for item in data_list:
            # 크롤러가 준 날짜(timestamp)를 가져옴, 없으면 현재 시간이라도 넣음
            notice_date = item.get("timestamp") 

            insert_data.append({
                "user_id": int(user_id),
                "title": item.get("title"),
                "summary": item.get("summary"),
                "source_name": item.get("sourceName"),
                "original_url": item.get("originalUrl"),
                "category": item.get("category"),
                "is_liked": True,
                # 🔴 공지사항 실제 날짜를 created_at 컬럼에 매핑!
                "created_at": notice_date 
            })

        if insert_data:
            # Supabase 저장 (여기서 진짜 DB에 들어감!)
            supabase.table("notifications").insert(insert_data).execute()
            print(f"✅ {user_id}번 유저 데이터 {len(insert_data)}건 DB 저장 완료")

        return {"status": "SUCCESS"}
        
    except Exception as e:
        print(f"💥 저장 실패: {str(e)}")
        return {"status": "ERROR", "message": str(e)}
    
def send_to_callback_list(callback_url: str, notices: List[dict], auth_token: str, user_id: int):
    scores = [float(item.get("relevanceScore", 0.0)) for item in notices]
    top_score = round(max(scores), 2) if scores else 0.0

    payload = {
        "status": "SUCCESS",
        "userId": str(user_id), # 저장할 때 필요한 userId 포함
        "relevanceScore": top_score,
        "data": notices
    }

    headers = {"Content-Type": "application/json", "X-AI-CALLBACK-TOKEN": auth_token}

    try:
        # 타임아웃 넉넉히 설정
        response = requests.post(callback_url, json=payload, headers=headers, timeout=30)
        print(f"📡 콜백 전송 완료 (상태코드: {response.status_code})")
    except Exception as e:
        print(f"❌ 콜백 전송 실패: {e}")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run("app.main:app", host="0.0.0.0", port=port, reload=True)


@app.post("/send-kakao")
async def send_daily_alarms():
    try:
        now = datetime.now()
        current_time = now.strftime("%H:%M:00") # 예: "09:00:00"

        # 1. 지금 시간이 alarm_time인 유저들 가져오기
        res = supabase.table("users").select("*").eq("alarm_time", current_time).execute()
        target_users = res.data

        for user in target_users:
            # 2. interval_days 체크 (예: 1일 주기면 매일, 3일 주기면 마지막 전송일 확인)
            # 여기서는 단순화를 위해 매일 전송으로 예시를 들게!
            
            # 3. notifications 테이블에서 아직 안 보낸 최신 알림 가져오기
            notis = supabase.table("notifications") \
                .select("*") \
                .eq("user_id", user["user_id"]) \
                .eq("is_sent", False) \
                .execute()

            if notis.data:
                # 4. 카카오톡 메시지 구성 및 전송 (API 호출)
                # kakao_api.send(user["phone_number"], notis.data)
                
                # 5. 보냈다고 표시
                supabase.table("notifications") \
                    .update({"is_sent": True}) \
                    .eq("user_id", user["user_id"]) \
                    .execute()

        return {"status": "SUCCESS", "processed_users": len(target_users)}
    except Exception as e:
        return {"status": "ERROR", "message": str(e)}