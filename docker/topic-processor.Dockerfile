FROM python:3.11-slim

WORKDIR /app

# 기본 의존성 설치
RUN apt-get update && \
    apt-get install -y \
    g++ \
    build-essential \
    git \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# 소스 코드 및 requirements 복사
COPY requirements.txt .

# Python 패키지 설치
RUN pip install --no-cache-dir -r requirements.txt

# BERTopic 관련 패키지 - CPU 전용 환경 최적화
RUN pip install --no-cache-dir \
    bertopic>=0.16.0 \
    hdbscan>=0.8.29 \
    umap-learn>=0.5.3 \
    pymongo>=4.0.0 \
    kafka-python>=2.0.0 \
    scikit-learn>=1.0.0 \
    joblib>=1.1.0

# 소스 코드 복사
COPY src/ src/

# 모델 저장 디렉토리 생성
RUN mkdir -p models

# 스레드 및 성능 최적화를 위한 환경 변수
ENV PYTHONUNBUFFERED=1
ENV OPENBLAS_NUM_THREADS=4
ENV MKL_NUM_THREADS=4
ENV OMP_NUM_THREADS=4
ENV NUMEXPR_NUM_THREADS=4

# 실행 명령
CMD ["python", "-m", "src.processors.topic.run_processor"] 