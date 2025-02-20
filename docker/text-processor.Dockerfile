FROM python:3.11-slim

WORKDIR /app

# mecab-ko 및 필요한 의존성 설치
RUN apt-get update && \
    apt-get install -y \
    g++ \
    build-essential \
    curl \
    git \
    wget \
    automake \
    autoconf \
    libtool \
    perl \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# mecab 설치
RUN wget "https://bitbucket.org/eunjeon/mecab-ko/downloads/mecab-0.996-ko-0.9.2.tar.gz" && \
    tar xvfz mecab-0.996-ko-0.9.2.tar.gz && \
    cd mecab-0.996-ko-0.9.2 && \
    ./configure && \
    make && \
    make check && \
    make install && \
    ldconfig && \
    cd .. && \
    rm -rf mecab-0.996-ko-0.9.2*

# mecab-ko-dic 설치
RUN wget "https://bitbucket.org/eunjeon/mecab-ko-dic/downloads/mecab-ko-dic-2.1.1-20180720.tar.gz" && \
    tar xvfz mecab-ko-dic-2.1.1-20180720.tar.gz && \
    cd mecab-ko-dic-2.1.1-20180720 && \
    ./autogen.sh && \
    ./configure && \
    make && \
    make install && \
    cd .. && \
    rm -rf mecab-ko-dic-2.1.1-20180720*

# 필요한 패키지 설치
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 소스 코드 복사
COPY src/ src/

# 환경 변수 설정
ENV PYTHONPATH=/app

# 실행 명령
CMD ["python", "-m", "src.processors.text.run_processor"] 