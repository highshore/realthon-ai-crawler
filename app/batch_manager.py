import requests
from supabase import create_client, Client
import os
from fastapi import APIRouter # main.py가 에러 안 나게 하기 위해 필요

# main.py에서 임포트할 때 에러 안 나게 라우터만 만들어둠
router = APIRouter()

# 1. Supabase 설정
SUPABASE_URL = os.getenv("SUPABASE_URL") 
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

CRAWLER_URL = "https://notice-alarm-service-567168557796.asia-northeast3.run.app/crawl/request"

def run_batch():
    try:
        res = supabase.table("users").select("*, target_urls(*)").eq("alarm_time", "09:00:00").execute()
        users = res.data
    except Exception as e:
        print(f"❌ DB 연결 실패: {e}")
        return

    for user in users:
        urls = [t['target_url'] for t in user.get('target_urls', [])]
        if not urls: continue

        payload = {
            "userId": int(user["user_id"]),
            "targetUrls": urls,
            "userProfile": {
                "username": user["username"],
                "phoneNumber": user.get("phone_number", "010-0000-0000"),
                "school": user["school"],
                "major": user["major"],
                "interestFields": ["IT"],
                "intervalDays": user["interval_days"],
                "alarmTime": "09:00"
            },
            "summary": "취업 공고 요약 요청",
            "callback": {
                "enabled": True,
                "callbackUrl": "https://notice-alarm-service-567168557796.asia-northeast3.run.app/callback/save",
                "authToken": "AI_CALLBACK_SECRET"
            }
        }

        print(f"📡 {user['username']}님 크롤링 요청 중...")
        try:
            response = requests.post(CRAWLER_URL, json=payload, timeout=60)
            print(f"✅ 결과: {response.status_code}")
        except Exception as e:
            print(f"❌ 에러: {e}")

if __name__ == "__main__":
    run_batch()