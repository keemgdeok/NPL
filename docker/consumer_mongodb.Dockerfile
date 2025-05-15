# 1. 기반 이미지 선택 (Python 3.12)
FROM python:3.12-slim

# 2. 작업 디렉토리 설정
WORKDIR /app

# 3. 필요한 Python 라이브러리 직접 설치
#    consumer_mongodb.py 및 의존하는 src/common/database 모듈에 필요한 라이브러리들입니다.
#    추가적으로 필요한 라이브러리가 있다면 여기에 추가해주세요.
RUN pip install --no-cache-dir \
    kafka-python \
    pymongo \
    pydantic \
    python-dotenv

# 4. 소스 코드 복사
#    src 디렉토리 전체를 이미지의 /app/src 로 복사합니다.
#    Dockerfile이 docker/ 내부에 있으므로, COPY의 소스 경로는 ../src/ 입니다.
COPY ../src/ ./src/

# 5. 실행할 스크립트 지정
#    PYTHONPATH를 설정하여 /app 에서 src.consumers 등을 찾을 수 있도록 합니다.
ENV PYTHONPATH=/app
CMD ["python", "src/consumers/consumer_mongodb.py"] 