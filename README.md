# 네이버 뉴스 분석기 (Naver News Analyzer)

## 프로젝트 개요
이 프로젝트는 네이버 뉴스를 수집하고 분석하여 토픽별 감정 분석을 수행하는 시스템입니다.

### 주요 기능
- 네이버 뉴스 실시간 수집 (API 및 웹 스크래핑)
- 토픽별 뉴스 분류 (정치, 경제, 사회, 문화/생활, IT/과학, 세계)
- 뉴스 내용 요약 및 주요 토픽 추출
- 감정 분석 및 통계
- 실시간 데이터 처리 및 시각화

## 기술 스택
- Python 3.9+
- AWS S3
- Apache Kafka
- Apache Airflow
- Docker
- Kubernetes
- FastAPI
- MongoDB/PostgreSQL

## 설치 방법
1. 저장소 클론
```bash
git clone [repository-url]
cd npl
```

2. 가상환경 생성 및 활성화
```bash
python -m venv venv
source venv/bin/activate  # Linux/Mac
# or
.\venv\Scripts\activate  # Windows
```

3. 의존성 설치
```bash
pip install -r requirements.txt
```

## 환경 설정
1. 환경 변수 설정
```bash
cp .env.example .env
# .env 파일을 적절히 수정
```

2. AWS 자격 증명 설정
3. Kafka 및 Airflow 설정

## 실행 방법
자세한 실행 방법은 추후 업데이트 예정

## 프로젝트 구조
```
.
├── src/
│   ├── collectors/      # 데이터 수집 관련 코드
│   ├── processors/      # 데이터 처리 및 분석 코드
│   ├── api/            # REST API 서버
│   └── dashboard/      # 대시보드 관련 코드
├── docker/             # Docker 설정 파일
├── k8s/                # Kubernetes 설정 파일
├── airflow_dags/       # Airflow DAG 파일들
├── tests/              # 테스트 코드
└── docs/              # 문서
```

## 라이선스
MIT License 