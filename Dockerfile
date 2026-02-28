# 1. 파이썬 환경 설정
FROM python:3.11-slim

# 2. 한글 및 로그 버퍼링 설정 (인코딩 에러 방지)
ENV LANG=C.UTF-8 \
    LC_ALL=C.UTF-8 \
    PYTHONIOENCODING=utf-8 \
    PYTHONUNBUFFERED=1

# 3. 필수 시스템 패키지 설치 (Tesseract OCR + Playwright 의존성)
RUN apt-get update && apt-get install -y \
    # 기존 Tesseract OCR 관련
    tesseract-ocr \
    tesseract-ocr-kor \
    libgl1 \
    # Playwright 및 브라우저 실행 관련 의존성
    libglib2.0-0 \
    libnss3 \
    libnspr4 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libdbus-1-3 \
    libxcb1 \
    libxkbcommon0 \
    libx11-6 \
    libxcomposite1 \
    libxdamage1 \
    libxext6 \
    libxfixes3 \
    librandr2 \
    libgbm1 \
    libpango-1.0-0 \
    libcairo2 \
    libasound2 \
    && rm -rf /var/lib/apt/lists/*

# 4. 작업 디렉토리 설정
WORKDIR /app

# 5. 종속성 설치
# requirements.txt에 playwright와 markdownify가 포함되어 있어야 합니다.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install --no-cache-dir fastapi uvicorn

# 6. Playwright 브라우저 설치 (Chromium만 설치하여 용량 최적화)
RUN playwright install chromium
RUN playwright install-deps chromium

# 7. 코드 복사
COPY . .

# 8. 실행 명령어
# app/main.py 안에 FastAPI 객체(app)가 있는 경우
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]