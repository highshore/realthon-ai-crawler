FROM python:3.11-slim
# 시스템 의존성 설치 (오타 방지를 위해 한 줄로 구성 권장)
RUN apt-get update && apt-get install -y \
    tesseract-ocr \
    tesseract-ocr-kor \
    libgl1 \
    libglib2.0-0 \
    && apt-get clean && rm -rf /var/lib/apt/lists/*


# 환경 변수 설정
ENV PYTHONPATH=/app
ENV LANG=C.UTF-8
ENV LC_ALL=C.UTF-8

WORKDIR /app

# 라이브러리 설치
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install numpy opencv-python pytesseract pillow

# 소스 복사
COPY . .

# 실행 명령어
CMD ["python", "app/jobs/korea_university.py"]