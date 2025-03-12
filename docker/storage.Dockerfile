FROM python:3.11-slim

# 작업 디렉토리 설정
WORKDIR /app

# 필요한 패키지 설치
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# 패키지 직접 설치
RUN pip install --no-cache-dir \
    kafka-python \
    aioboto3 \
    boto3 \
    botocore \
    python-dotenv>=1.0.0

# 소스 코드 복사
COPY src/ src/

# 환경 변수 설정
ENV PYTHONUNBUFFERED=1

# 실행 명령
CMD ["python", "-m", "src.collectors.storage", "--run-once", "--wait-empty", "30"] 
