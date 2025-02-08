FROM python:3.11-slim

WORKDIR /app

# 필요한 패키지 설치
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 소스 코드 복사
COPY src/ src/

# 환경 변수 설정
ENV PYTHONPATH=/app

# 포트 설정
EXPOSE 8000

# 실행 명령
CMD ["python", "-m", "src.api.run_api", "--host", "0.0.0.0", "--port", "8000"] 