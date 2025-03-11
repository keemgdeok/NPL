#!/bin/bash
set -e

# 색상 정의
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${GREEN}데이터 파이프라인 Airflow 설치 및 실행 스크립트${NC}"
echo "===================================="

# 필요한 디렉토리 확인 및 생성
echo -e "${YELLOW}필요한 디렉토리 확인 중...${NC}"

# 각 디렉토리 존재 여부 확인 후 필요시에만 생성
for dir in "./airflow/dags" "./airflow/logs" "./airflow/plugins" "./airflow/config/variables" "./airflow/models"; do
  if [ ! -d "$dir" ]; then
    echo "디렉토리 생성: $dir"
    mkdir -p "$dir"
  else
    echo "디렉토리 확인: $dir (이미 존재함)"
  fi
done

# DAG 파일 복사 (이미 존재하는 경우 스킵)
echo -e "${YELLOW}DAG 파일 복사 중...${NC}"
if [[ -f ./news_pipeline_dag.py ]]; then
  if [[ -f ./airflow/dags/news_pipeline_dag.py ]]; then
    echo "news_pipeline_dag.py 파일이 이미 존재합니다. 복사하지 않습니다."
  else
    cp ./news_pipeline_dag.py ./airflow/dags/
    echo "news_pipeline_dag.py 파일을 복사했습니다."
  fi
fi

if [[ -f ./news_monitoring_dag.py ]]; then
  if [[ -f ./airflow/dags/news_monitoring_dag.py ]]; then
    echo "news_monitoring_dag.py 파일이 이미 존재합니다. 복사하지 않습니다."
  else
    cp ./news_monitoring_dag.py ./airflow/dags/
    echo "news_monitoring_dag.py 파일을 복사했습니다."
  fi
fi

# 변수 파일 복사 (이미 존재하는 경우 스킵)
echo -e "${YELLOW}변수 파일 복사 중...${NC}"
if [[ -f ./airflow_variables.json ]]; then
  if [[ -f ./airflow/config/variables/airflow_variables.json ]]; then
    echo "airflow_variables.json 파일이 이미 존재합니다. 복사하지 않습니다."
  else
    cp ./airflow_variables.json ./airflow/config/variables/
    echo "airflow_variables.json 파일을 복사했습니다."
  fi
fi

# Docker 네트워크 생성 (없는 경우)
if ! docker network ls | grep -q npl-network; then
  echo -e "${YELLOW}Docker 네트워크 'npl-network' 생성 중...${NC}"
  docker network create npl-network
else
  echo -e "${YELLOW}Docker 네트워크 'npl-network'가 이미 존재합니다.${NC}"
  # 기존 컨테이너 중지
  echo -e "${YELLOW}기존 Airflow 컨테이너 정리 중...${NC}"
  docker compose -f docker-compose-airflow.yml down --volumes --remove-orphans
fi

# Docker 이미지 미리 가져오기
echo -e "${YELLOW}Airflow Docker 이미지 가져오는 중...${NC}"
docker pull apache/airflow:2.10.5-python3.11
# 이미지 검증
if ! docker image inspect apache/airflow:2.10.5-python3.11 &>/dev/null; then
  echo -e "${RED}Airflow 이미지를 가져오는데 실패했습니다.${NC}"
  exit 1
fi

# Airflow 구성
echo -e "${YELLOW}Airflow 초기화 중...${NC}"
echo -e "${YELLOW}이 작업은 몇 분 정도 소요될 수 있습니다. 기다려 주세요...${NC}"
docker compose -f docker-compose-airflow.yml up airflow-init

echo -e "${GREEN}Airflow 초기화 완료!${NC}"
echo "===================================="
echo -e "${YELLOW}Airflow 서비스 시작 명령어:${NC}"
echo "docker compose -f docker-compose-airflow.yml up -d"
echo ""
echo -e "${YELLOW}Airflow UI 접속 정보:${NC}"
echo "URL: http://localhost:8081"
echo "Username: airflow"
echo "Password: airflow"
echo ""

echo -e "${GREEN}시작하시겠습니까? (y/n)${NC}"
read answer

if [[ "$answer" == "y" ]] || [[ "$answer" == "Y" ]]; then
  echo -e "${YELLOW}Airflow 서비스 시작 중...${NC}"
  docker compose -f docker-compose-airflow.yml up -d
  echo -e "${GREEN}Airflow 서비스가 시작되었습니다!${NC}"
  echo "웹 UI: http://localhost:8080 (사용자명: airflow, 비밀번호: airflow)"
  
  # 서비스가 완전히 시작될 때까지 대기
  echo -e "${YELLOW}서비스 시작 대기 중... (15초)${NC}"
  sleep 15
  
  # 변수 자동 업로드
  echo -e "${YELLOW}Airflow 변수 자동 업로드 중...${NC}"
  if [[ -f ./airflow/config/variables/airflow_variables.json ]]; then
    if docker exec -i npl-airflow-webserver airflow variables import /opt/airflow/config/variables/airflow_variables.json; then
      echo -e "${GREEN}변수가 성공적으로 업로드되었습니다!${NC}"
    else
      echo -e "${RED}변수 업로드 실패. 웹 UI에서 수동으로 가져오세요.${NC}"
      echo "Admin > Variables > Import Variables 메뉴에서 airflow_variables.json 파일을 가져오세요."
    fi
  else
    echo -e "${RED}변수 파일을 찾을 수 없습니다.${NC}"
  fi
  
  # 로그 확인 방법 안내
  echo -e "\n${YELLOW}문제가 발생한 경우 다음 명령어로 로그를 확인하세요:${NC}"
  echo "웹서버 로그: docker logs npl-airflow-webserver"
  echo "스케줄러 로그: docker logs npl-airflow-scheduler"
  echo "초기화 로그: docker logs npl-airflow-init"
  
  # 컨테이너 상태 확인 방법 안내
  echo -e "\n${YELLOW}컨테이너 상태 확인:${NC}"
  echo "docker ps | grep airflow"
  
  # 접속 확인 팁
  echo -e "\n${YELLOW}접속 확인 팁:${NC}"
  echo "웹 UI가 접속되지 않는 경우 30초~1분 정도 기다려 보세요."
  echo "WSL을 사용 중이라면, http://localhost:8081 대신 WSL IP를 사용해 보세요:"
  echo "WSL IP 확인: ip addr show eth0 | grep -oP '(?<=inet\s)\d+(\.\d+){3}'"
  
else
  echo -e "${YELLOW}서비스 시작이 취소되었습니다. 나중에 다음 명령어로 시작할 수 있습니다:${NC}"
  echo "docker compose -f docker-compose-airflow.yml up -d"
fi 