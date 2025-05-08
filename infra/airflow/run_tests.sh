#!/bin/bash
# Airflow DAG 테스트 실행 스크립트

# 색상 정의
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${GREEN}Airflow DAG 테스트 실행 스크립트${NC}"
echo "===================================="

# 도커 사용 여부 확인
USE_DOCKER=false
if [ "$1" == "--docker" ]; then
  USE_DOCKER=true
  echo -e "${YELLOW}도커 환경에서 테스트를 실행합니다.${NC}"
fi

# 직접 실행 모드 (도커 없이)
if [ "$USE_DOCKER" = false ]; then
  # 가상 환경 확인
  if [ ! -d "venv" ]; then
    echo -e "${YELLOW}가상 환경을 생성합니다...${NC}"
    python -m venv venv
  fi

  # 가상 환경 활성화
  echo -e "${YELLOW}가상 환경을 활성화합니다...${NC}"
  source venv/bin/activate
  
  # 의존성 설치
  echo -e "${YELLOW}테스트 의존성을 설치합니다...${NC}"
  pip install -r test_requirements.txt
  
  # 임시 테스트 디렉토리 생성
  if [ ! -d ".airflow-test" ]; then
    mkdir -p .airflow-test/dags
    mkdir -p .airflow-test/logs
    mkdir -p .airflow-test/plugins
  fi
  
  # Airflow 초기화 (필요시)
  export AIRFLOW_HOME=$(pwd)/.airflow-test
  export AIRFLOW__CORE__DAGS_FOLDER=$(pwd)/dags
  export AIRFLOW__CORE__LOAD_EXAMPLES=False
  
  # 테스트 실행
  echo -e "${YELLOW}DAG 테스트를 실행합니다...${NC}"
  pytest -xvs dags/test_*.py
  TEST_EXIT_CODE=$?
  
  # 테스트 결과 보고
  if [ $TEST_EXIT_CODE -eq 0 ]; then
    echo -e "${GREEN}모든 테스트가 성공적으로 완료되었습니다!${NC}"
  else
    echo -e "${RED}일부 테스트가 실패했습니다. 위의 오류 메시지를 확인하세요.${NC}"
  fi
  
  # 정리
  echo -e "${YELLOW}가상 환경을 비활성화합니다...${NC}"
  deactivate
  
  exit $TEST_EXIT_CODE
fi

# 도커 실행 모드
if [ "$USE_DOCKER" = true ]; then
  echo -e "${YELLOW}도커 컨테이너에서 테스트를 실행합니다...${NC}"
  
  # 도커 이미지 빌드 (간단한 Dockerfile 생성)
  if [ ! -f "Dockerfile.test" ]; then
    echo -e "${YELLOW}테스트용 Dockerfile 생성...${NC}"
    cat > Dockerfile.test << EOF
FROM apache/airflow:2.10.5-python3.11
USER root
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*
USER airflow
WORKDIR /opt/airflow
COPY test_requirements.txt .
RUN pip install --no-cache-dir -r test_requirements.txt
COPY . .
EOF
  fi
  
  # 도커 이미지 빌드
  echo -e "${YELLOW}테스트 이미지를 빌드합니다...${NC}"
  docker build -f Dockerfile.test -t npl-airflow-test .
  
  # 도커 컨테이너에서 테스트 실행
  echo -e "${YELLOW}테스트를 실행합니다...${NC}"
  docker run --rm \
    -v $(pwd)/dags:/opt/airflow/dags \
    -v $(pwd)/pytest.ini:/opt/airflow/pytest.ini \
    npl-airflow-test \
    pytest -xvs dags/test_*.py
  
  TEST_EXIT_CODE=$?
  
  # 테스트 결과 보고
  if [ $TEST_EXIT_CODE -eq 0 ]; then
    echo -e "${GREEN}모든 테스트가 성공적으로 완료되었습니다!${NC}"
  else
    echo -e "${RED}일부 테스트가 실패했습니다. 위의 오류 메시지를 확인하세요.${NC}"
  fi
  
  exit $TEST_EXIT_CODE
fi 
 