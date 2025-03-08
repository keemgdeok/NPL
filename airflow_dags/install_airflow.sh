#!/bin/bash
set -e

# 색상 정의
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${GREEN}뉴스 파이프라인 Airflow 설치 스크립트${NC}"
echo "===================================="

# 필요한 디렉토리 생성
echo -e "${YELLOW}필요한 디렉토리 생성 중...${NC}"
mkdir -p ./airflow/dags
mkdir -p ./airflow/logs
mkdir -p ./airflow/plugins
mkdir -p ./airflow/config
mkdir -p ./airflow/models

# 권한 설정
echo -e "${YELLOW}권한 설정 중...${NC}"
# Linux 환경에서 필요한 AIRFLOW_UID 설정
if [[ $(uname) == "Linux" ]]; then
  AIRFLOW_UID=$(id -u)
  echo "AIRFLOW_UID=$AIRFLOW_UID" > .env
  echo "Airflow UID를 $AIRFLOW_UID으로 설정했습니다"
else
  echo "AIRFLOW_UID=50000" > .env
  echo "기본 Airflow UID를 50000으로 설정했습니다"
fi

# DAG 파일 복사
echo -e "${YELLOW}DAG 파일 복사 중...${NC}"
cp ./news_pipeline_dag.py ./airflow/dags/
cp ./news_monitoring_dag.py ./airflow/dags/
# 변수 파일 복사
mkdir -p ./airflow/config/variables
cp ./airflow_variables.json ./airflow/config/variables/

# Airflow 구성
echo -e "${YELLOW}Airflow 초기화 중...${NC}"
docker-compose -f docker-compose-airflow.yml up airflow-init

echo -e "${GREEN}Airflow 초기화 완료!${NC}"
echo "===================================="
echo -e "${YELLOW}Airflow 서비스 시작 명령어:${NC}"
echo "docker-compose -f docker-compose-airflow.yml up -d"
echo ""
echo -e "${YELLOW}Airflow UI 접속 정보:${NC}"
echo "URL: http://localhost:8081"
echo "Username: airflow"
echo "Password: airflow"
echo ""
echo -e "${YELLOW}참고: kafka-ui는 http://localhost:8080 에서 접속 가능합니다.${NC}"
echo ""
echo -e "${YELLOW}설치가 완료되었습니다. 변수 가져오기:${NC}"
echo "Airflow UI에서 Admin > Variables > Import Variables에서 airflow_variables.json 파일을 가져오세요."
echo ""
echo -e "${GREEN}시작하시겠습니까? (y/n)${NC}"
read answer

if [[ "$answer" == "y" ]] || [[ "$answer" == "Y" ]]; then
  echo -e "${YELLOW}Airflow 서비스 시작 중...${NC}"
  docker-compose -f docker-compose-airflow.yml up -d
  echo -e "${GREEN}Airflow 서비스가 시작되었습니다!${NC}"
  echo "웹 UI: http://localhost:8081 (사용자명: airflow, 비밀번호: airflow)"
else
  echo -e "${YELLOW}서비스 시작이 취소되었습니다. 나중에 다음 명령어로 시작할 수 있습니다:${NC}"
  echo "docker-compose -f docker-compose-airflow.yml up -d"
fi 