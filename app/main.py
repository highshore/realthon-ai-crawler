import os
import requests
import uvicorn
import json
from fastapi import FastAPI
from pydantic import BaseModel, Field
from typing import List, Optional

# 크롤링 로직 임포트
from app.jobs.korea_university import run 

app = FastAPI()

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
    userId: str
    targetUrls: List[str]  # targetUrl(str)에서 targetUrls(List[str])로 변경!
    userProfile: UserProfile
    summary: str
    callback: CallbackConfig
@app.post("/crawl/request")
async def handle_crawl(request_data: BatchRequest):
    try:
        data_dict = request_data.model_dump()
        
        # [수정 1] event에 넘길 때도 단수가 아니라 복수(targetUrls)로 넘겨야 함
        event = {
            "userId": data_dict["userId"],
            "targetUrls": data_dict["targetUrls"], # targetUrl -> targetUrls
            "userProfile": data_dict["userProfile"],
            "callbackUrl": data_dict["callback"]["callbackUrl"]
        }
        
        # [수정 2] 로그 찍을 때도 리스트 전체를 보여주거나 첫 번째 걸 찍어야 함
        print(f"DEBUG: 크롤링 시작 (URLs: {data_dict['targetUrls']})")
        
        # 이제 run(event) 내부에서 targetUrls 리스트를 돌며 크롤링함
        result = run(event)
        
        if not result or result.get("status") != "SUCCESS":
            msg = result.get("message") if result else "결과 없음"
            print(f"⚠️ 건너뜀: {msg}")
            return {"status": "SKIPPED", "message": msg}

        # [데이터 전송] 
        if data_dict["callback"]["enabled"]:
            actual_notices = result.get("data", [])
            
            if actual_notices:
                # 여기서 은서님 서버로 데이터 쏨
                send_to_callback_list(
                    data_dict["callback"]["callbackUrl"],
                    actual_notices,
                    data_dict["callback"]["authToken"]
                )
            else:
                print("⚠️ 적합한 공지가 없어 콜백을 생략합니다.")
            
        return {"status": "SUCCESS", "count": len(result.get("data", []))}
        
    except Exception as e:
        print(f"💥 서버 에러: {str(e)}")
        import traceback
        print(traceback.format_exc()) # 에러 위치 정확히 보려고 추가
        return {"status": "ERROR", "message": str(e)}
def send_to_callback_list(callback_url: str, notices: List[dict], auth_token: str):
    # 결과 점수 계산
    scores = [float(item.get("relevanceScore", 0.0)) for item in notices]
    top_score = round(max(scores), 2) if scores else 0.0

    # 콜백 페이로드 준비
    payload = {
        "status": "SUCCESS",
        "relevanceScore": top_score,
        "data": notices
    }

    # (선택) 디버그 출력
    print(json.dumps(payload, ensure_ascii=False, indent=2))

    headers = {
        "Content-Type": "application/json",
        "X-AI-CALLBACK-TOKEN": auth_token
    }

    # 실제 콜백 전송
    try:
        response = requests.post(callback_url, json=payload, headers=headers, timeout=60)
        print(f"📡 콜백 응답 코드: {response.status_code}")
    except Exception as e:
        print(f"❌ 콜백 전송 실패: {e}")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run("app.main:app", host="0.0.0.0", port=port)