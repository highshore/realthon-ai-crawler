from fastapi import FastAPI, Request
import uvicorn
import os
import sys
from fastapi.middleware.cors import CORSMiddleware
# 기존 jobs 경로에 있는 run 함수를 가져옵니다.
# 경로가 app.jobs.korea_university 인지 확인하세요.
from app.jobs.korea_university import run

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # 실제 배포 시에는 프론트엔드 도메인만 허용하는 게 좋습니다.
    allow_methods=["*"],
    allow_headers=["*"],
)
@app.get("/")
def root():
    return {"message": "Crawler Service is Running"}
from pydantic import BaseModel
from typing import Any, Dict

# 1. 입력 데이터 구조 정의 (Pydantic 모델)
class CrawlRequest(BaseModel):
    userId: str = "user_12345"
    targetUrl: str = "https://info.korea.ac.kr/info/board/notice_under.do"
    userProfile: Dict[str, Any] = {
        "username": "양은서",
        "major": "컴퓨터공학과",
        "interestFields": ["AI", "BACKEND"],
        "summary": "AI 및 데이터 시각화에 관심이 많은 개발자"
    }
    config: Dict[str, Any] = {"language": "Korean"}

# 2. 엔드포인트 수정 (Request 대신 CrawlRequest 사용)
@app.post("/crawl")
async def handle_crawl(request_data: CrawlRequest): # 이렇게 써야 입력창이 생깁니다!
    try:
        # Pydantic 모델을 딕셔너리로 변환하여 기존 run 함수에 전달
        event = request_data.model_dump() 
        result = run(event)
        return result
    except Exception as e:
        return {"status": "ERROR", "message": str(e)}

if __name__ == "__main__":
    # Cloud Run은 8080 포트를 통해 통신합니다.
    port = int(os.environ.get("PORT", 8080))
    # log_level을 info로 설정하여 실행 로그를 확인합니다.
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")