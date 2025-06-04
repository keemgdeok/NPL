# ================================
# 1단계: 빌드 스테이지
# ================================
FROM nvidia/cuda:12.1.0-cudnn8-devel-ubuntu22.04 AS builder

# Python 설치 (CUDA 이미지에는 Python이 기본 포함되지 않음)
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    python3.11 \
    python3.11-dev \
    python3.11-venv \
    python3-pip \
    build-essential \
    gcc \
    git \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# 가상환경 생성
RUN python3.11 -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# 필수 파이썬 라이브러리 설치 (GPU 버전 + PyYAML 추가)
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir \
    torch>=2.0.1 \
    transformers>=4.34.0 \
    kafka-python>=2.0.2 \
    python-dotenv>=1.0.0 \
    PyYAML>=6.0 \
    numpy>=1.24.4 \
    tqdm>=4.66.1 \
    nltk>=3.8.1

# 소스 코드 복사
COPY src/ /app/src/

# NLTK punkt 다운로드 (setup.py 실행)
WORKDIR /app
ENV PYTHONPATH=/app
RUN python -m src.processors.summary.setup

# ================================
# 2단계: 실행 스테이지
# ================================
FROM nvidia/cuda:12.1.0-cudnn8-runtime-ubuntu22.04

# Python 설치
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    python3.11 \
    python3.11-venv \
    python3-pip \
    curl \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 이전 스테이지에서 빌드된 가상환경 복사
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# 소스 코드 복사
COPY src/ /app/src/

# 환경 변수 설정
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1
ENV NVIDIA_VISIBLE_DEVICES=all
ENV NVIDIA_DRIVER_CAPABILITIES=compute,utility
ENV COMPONENT_NAME="summary-processor"

# 컨테이너 시작 시 헬스체크 지원
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD curl -f http://localhost:8000/health || exit 1

# 설정 파일 기반으로 실행 (기본 설정 파일 사용)
CMD ["python3", "-m", "src.processors.summary.run_processor"] 