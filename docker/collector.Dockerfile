FROM python:3.11-slim

WORKDIR /app

# 필수 시스템 패키지 설치 (빌드 도구 및 의존성)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# 수집기에 필요한 Python 라이브러리 설치
RUN pip install --no-cache-dir \
    aiohttp>=3.9.1 \
    beautifulsoup4>=4.12.2 \
    kafka-python>=2.0.2 \
    pymongo>=4.6.1 \
    aioboto3>=11.3.0 \
    python-dotenv>=1.0.0 \
    tenacity>=8.2.3

# 소스 코드 복사
COPY src/ src/

# 환경 변수 설정
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1
ENV KAFKA_BOOTSTRAP_SERVERS=kafka:29092
ENV KAFKA_CONNECTION_RETRY=5
ENV KAFKA_CONNECTION_RETRY_DELAY=5

# 실행 명령
CMD ["python", "-m", "src.collectors.run_collector", "--kafka-servers=kafka:29092", "--interval=3600"] 