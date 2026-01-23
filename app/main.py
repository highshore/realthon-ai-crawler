from fastapi import FastAPI, Request
import uvicorn
import os
import sys
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field # Field 추가: 유효성 검사 및 설명용
from typing import Any, Dict, List

# 기존 jobs 경로에 있는 run 함수를 가져옵니다.
from app.jobs.korea_university import run

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- 1. 입력 데이터 구조 정의 (Pydantic 모델) ---
class UserProfile(BaseModel):
    # 실제 연동 시: Optional을 써서 데이터가 없어도 에러가 나지 않게 하거나, 
    # 기본값을 제거하여 필수값으로 지정할 수 있습니다.
    username: str
    school: str = "이화여자대학교"
    major: str
    interestFields: List[str]
    intervalDays: int = 3 # 알림 주기 (lookback 기간으로 활용)
    alarmTime: str = "09:30:00"

class CrawlRequest(BaseModel):
    # 실제 연동 시: 백엔드에서 넘겨줄 실제 필드명과 일치시켜야 합니다.
    userId: str = Field(..., description="사용자 식별 고유 ID")
    targetUrl: str = Field(..., description="크롤링 대상 게시판 URL")
    userProfile: UserProfile # 중첩 모델을 사용하여 구조를 체계화합니다.
    config: Dict[str, Any] = {"language": "Korean"}

@app.get("/")
def root():
    return {"message": "Crawler Service is Running"}

# --- 2. 엔드포인트 ---
@app.post("/crawl")
async def handle_crawl(request_data: CrawlRequest): 
    """
    실제 JSON 수신 프로세스:
    1. 외부(Cloud Scheduler/BE)에서 POST 요청을 보냄 (Body에 JSON 포함)
    2. FastAPI가 CrawlRequest 모델에 맞춰 JSON 파싱 및 유효성 검사 실시
    3. 검사 통과 시 아래 로직 실행, 실패 시 422 Unprocessable Entity 에러 자동 반환
    """
    try:
        # pydantic 모델을 dict로 변환 (기존 run 함수와의 호환성)
        event = request_data.model_dump() 
        
        # 실제 운영 팁: run 함수 내부에서 event['userProfile']['intervalDays']를 사용하여
        # '오늘 - intervalDays' 날짜 이후의 게시물만 필터링하도록 로직을 보강하세요.
        result = run(event)
        
        return result
    except Exception as e:
        # 실전: 로그 시스템(GCP Cloud Logging 등)에 에러를 남기는 것이 중요합니다.
        print(f"Error occurred: {str(e)}")
        return {"status": "ERROR", "message": "Internal Server Error"}

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")