FROM python:3.11-slim

WORKDIR /app

# CUDA 관련 패키지 설치
RUN apt-get update && \
    apt-get install -y g++ build-essential curl git && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# 필요한 패키지 설치
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 소스 코드 복사
COPY src/ src/

# 환경 변수 설정
ENV PYTHONPATH=/app

# 실행 명령
CMD ["python", "-m", "src.processors.sentiment.run_processor"] 