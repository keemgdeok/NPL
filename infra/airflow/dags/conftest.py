"""
Airflow DAG 테스트를 위한 공통 픽스처

이 모듈은 Airflow DAG 테스트에 필요한 공통 픽스처를 정의
"""

import pytest
from unittest import mock
from datetime import datetime

from unittest.mock import patch
from airflow.models.dagbag import DagBag


# Variable.get 패치를 준비하는 픽스처
@pytest.fixture(scope="session") 
def variable_patch_context(): 
    variable_defaults = {
        'EMAIL_NOTIFICATION': 'test-user@example.com', # 테스트 기대값과 일치
        'KAFKA_BOOTSTRAP_SERVERS': 'mock_kafka:9092',
        'MONGODB_URI': 'mongodb://mock_user:mock_pass@mock_mongo:27017',
        'DATABASE_NAME': 'mock_db',
        'DOCKER_NETWORK': 'mock-network',
        'PROJECT_PATH': '/mock/project/path',
        'AWS_ACCESS_KEY_ID': 'mock_aws_key_id',
        'AWS_SECRET_ACCESS_KEY': 'mock_aws_secret_key',
        'AWS_REGION': 'mock-region-1',
        'S3_BUCKET_NAME': 'mock-s3-bucket',
        'MODEL_PVC_NAME': 'mock-airflow-models-pvc',
        'K8S_NAMESPACE': 'mock-airflow-ns',
        'AWS_K8S_SECRET_NAME': 'mock-aws-credentials',
        # monitoring_dag.py 에서 사용하는 Variable 추가
        'MONITORING_IMAGE': 'mock-monitoring-image:latest',
        'MONGODB_K8S_SECRET_NAME': 'mock-mongodb-credentials',
        'SLACK_K8S_SECRET_NAME': 'mock-slack-webhook',
        'TEAMS_K8S_SECRET_NAME': 'mock-teams-webhook',
        'AIRFLOW_WORKER_IMAGE': 'mock-airflow-worker-image:latest', 
    }
    def get_variable_side_effect(name, default_var=None):
        if name in variable_defaults:
            return variable_defaults[name]
        if default_var is not None:
            return default_var
        raise KeyError(f"Mock Variable: {name} not found and no default_var provided.")
    
    # patch 객체를 반환
    return patch('airflow.models.Variable.get', side_effect=get_variable_side_effect)

# dagbag 픽스처 수정: variable_patch_context를 사용하여 DagBag 생성 감싸기
@pytest.fixture(scope="session")
def dagbag(variable_patch_context): # variable_patch_context 픽스처 주입
    """테스트용 DagBag 객체를 반환합니다 (Variable.get 패치 적용)."""
    dags_folder = "/mnt/c/Users/keemg/npl/infra/airflow/dags" 
    
    # patch 활성화 상태에서 DagBag 생성 및 파싱 수행
    with variable_patch_context:
        the_dagbag = DagBag(
            dag_folder=dags_folder, 
            include_examples=False, 
            read_dags_from_db=False # DB 접근 없이 순수하게 파일만 파싱
        )

    # with 블록 벗어나면 patch 비활성화, 하지만 DAG 객체는 이미 파싱됨
    return the_dagbag


# 테스트 컨텍스트 픽스처
@pytest.fixture
def test_context():
    """테스트용 Airflow 태스크 컨텍스트를 생성합니다."""
    context = {
        'ds': '2023-01-01',
        'ts': '2023-01-01T00:00:00+00:00',
        'execution_date': datetime(2023, 1, 1),
        'task_instance': mock.MagicMock(),
        'dag_run': mock.MagicMock(),
        'dag': mock.MagicMock(),
        'params': {},
    }
    
    # xcom_pull 모의 설정
    context['task_instance'].xcom_pull.return_value = None
    
    return context


# MongoDB 모의 클라이언트 픽스처
@pytest.fixture
def mock_mongo_client():
    """MongoDB 클라이언트를 모의로 생성합니다."""
    with mock.patch('pymongo.MongoClient') as mock_client:
        # 모의 DB 및 컬렉션 설정
        mock_db = mock_client.return_value.__getitem__.return_value
        mock_db.command.return_value = {"ok": 1}
        mock_db.list_collection_names.return_value = [
            "test_news_articles", "test_processed_articles", 
            "test_sentiment_articles", "test_summary_articles"
        ]
        
        # 모의 컬렉션 설정
        mock_collection = mock_db.__getitem__.return_value
        mock_collection.count_documents.return_value = 100
        
        yield mock_client


# Kafka 모의 클라이언트 픽스처
@pytest.fixture
def mock_kafka_client():
    """Kafka 프로듀서 및 컨슈머를 모의로 생성합니다."""
    with mock.patch('kafka.KafkaProducer') as mock_producer, \
         mock.patch('kafka.KafkaConsumer') as mock_consumer:
        
        # 프로듀서 모의 설정
        mock_producer.return_value.send.return_value = mock.MagicMock()
        
        # 컨슈머 모의 설정
        mock_consumer.return_value.topics.return_value = set([
            "news-collected", "news-processed", "news-sentiment", "news-summary"
        ])
        
        yield mock_producer, mock_consumer 

