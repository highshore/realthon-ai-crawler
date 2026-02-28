🚀 AI 공지사항 스마트 알리미 (Notice Alarm Service)
이 프로젝트는 대학교 공지사항을 수집하고, Gemini AI로 맞춤형 정보를 선별하여 Supabase DB에 저장한 뒤, 사용자별 설정 시간에 맞춰 **카카오 알림톡(NHN Cloud)**으로 요약 발송하는 GCP Cloud Run 기반의 풀스택 자동화 서비스입니다.

🏗️ 시스템 아키텍처 및 워크플로우
Crawl Dispatcher: Cloud Scheduler가 /scheduler/dispatch-crawl을 호출하여 모든 유저의 크롤링을 시작합니다.

AI 분석 및 필터링: Gemini가 유저 프로필과 공지 제목을 대조하여 적합도 점수(0.0~1.0)를 매깁니다.

Data Storage (Callback): 분석된 공지 중 중복되지 않은 신규 데이터만 Supabase notifications 테이블에 is_sent=False 상태로 저장합니다.

Smart Notification: 설정된 알람 시간(예: 15:00)이 되면 /scheduler/send-notifications가 작동합니다.

Batch Messaging: 한 유저에게 쌓인 여러 개의 신규 공지를 하나의 카카오 알림톡으로 묶어서 발송하여 피로도를 낮추고 비용을 절감합니다.

📂 주요 파일 구조 및 역할
app/main.py: 서비스의 메인 컨트롤러. API 엔드포인트 정의 및 전체 프로세스 오케스트레이션.

app/jobs/korea_university.py: 고려대학교 맞춤형 크롤링 및 AI 분석 핵심 로직.

주요 엔드포인트:

/scheduler/dispatch-crawl: 전체 유저 대상 크롤링 트리거.

/callback/save: 크롤링 결과 수신 및 Supabase DB 저장 (중복 체크 포함).

/scheduler/send-notifications: 유저별 알람 시간대에 맞춘 카톡 묶음 발송.

🛠️ 설치 및 로컬 실행 방법
1. 필수 요구사항
Python 3.10+

Tesseract OCR 엔진 (이미지 분석용)

2. 환경 변수 설정 (.env)
코드 스니펫
# AI & Database
GEMINI_API_KEY=your_key
SUPABASE_URL=your_url
SUPABASE_KEY=your_key

# Kakao Alimtalk (NHN Cloud)
KAKAO_SENDER_KEY=your_sender_key
KAKAO_SECRET_KEY=your_secret_key
KAKAO_APP_KEY=your_app_key

# Environment
BASE_URL="https://notice-alarm-service-567168557796.asia-northeast3.run.app"
PORT=8080
3. 로컬 실행
Bash
# 가상환경 활성화 후
$env:PYTHONPATH += ";."
python app/main.py
📡 API 규격 (Key Interfaces)
POST /scheduler/send-notifications
현재 시간대에 설정된 유저들에게 알림을 발송합니다. (Cloud Scheduler 전용)

작동 로직:

users 테이블에서 alarm_time이 현재 '시(Hour)'와 일치하는 유저 조회.

notifications 테이블에서 is_sent=False인 해당 유저의 공지 수집.

최대 n개의 제목을 줄바꿈(\n)으로 묶어 카카오 알림톡 전송.

전송 성공 시 해당 공지들의 is_sent를 True로 업데이트.

💡 개발 및 운영 가이드 (Note)
중복 발송 방지: notifications 테이블의 original_url을 기준으로 중복 저장을 방지하며, 발송 후 즉시 상태값을 변경하여 안정성을 확보했습니다.

비용 최적화: 낱개 발송이 아닌 **묶음 발송(Batching)**을 통해 알림톡 발송 비용을 획기적으로 줄였습니다.

유연한 시간 매칭: 스케줄러 실행 시 분 단위 오차를 허용하기 위해 '시(Hour)' 단위 매칭 로직을 적용했습니다.

