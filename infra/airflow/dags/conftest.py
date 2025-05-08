"""
Airflow DAG 테스트를 위한 공통 픽스처

이 모듈은 Airflow DAG 테스트에 필요한 공통 픽스처를 정의합니다.
"""
import os
import pytest
from unittest import mock
from datetime import datetime

from airflow.models import DagBag, Variable, Connection
from airflow.utils.session import create_session


# DAG 백 픽스처
@pytest.fixture
def dagbag():
    """테스트용 DagBag 객체를 반환합니다."""
    return DagBag(dag_folder="/opt/airflow/dags", include_examples=False)


# 환경 변수 모의 설정
@pytest.fixture(scope="session", autouse=True)
def mock_env_variables():
    """테스트에 필요한 환경 변수를 모의 설정합니다."""
    with mock.patch.dict("os.environ", {
        "AIRFLOW__CORE__FERNET_KEY": "mock_fernet_key",
        "AIRFLOW_CONN_MONGODB": "mongodb://mock:27017/mock_db",
        "KAFKA_BOOTSTRAP_SERVERS": "mock-kafka:9092",
        "MONGODB_NEWS_COLLECTION": "test_news_articles",
        "MONGODB_PROCESSED_COLLECTION": "test_processed_articles",
        "MONGODB_SENTIMENT_COLLECTION": "test_sentiment_articles",
        "MONGODB_SUMMARY_COLLECTION": "test_summary_articles",
        "AWS_S3_BUCKET_NAME": "test-news-bucket",
        "SLACK_WEBHOOK_URL": "https://mock-slack-webhook.com/test",
        "MS_TEAMS_WEBHOOK_URL": "https://mock-teams-webhook.com/test",
        "ALERT_EMAIL_RECIPIENTS": "test@example.com"
    }):
        yield


# Airflow 변수 모의 설정
@pytest.fixture(scope="function", autouse=True)
def mock_airflow_variables():
    """테스트에 필요한 Airflow 변수를 모의 설정합니다."""
    with mock.patch.object(Variable, "get") as mock_var_get:
        def variable_side_effect(key, default=None):
            """Variable.get 호출에 대한 사이드 이펙트 함수"""
            test_variables = {
                "KAFKA_BOOTSTRAP_SERVERS": "mock-kafka:9092",
                "MONGODB_URI": "mongodb://mock:27017/mock_db",
                "DATABASE_NAME": "mock_db",
                "MONGODB_NEWS_COLLECTION": "test_news_articles",
                "MONGODB_PROCESSED_COLLECTION": "test_processed_articles",
                "MONGODB_SENTIMENT_COLLECTION": "test_sentiment_articles",
                "MONGODB_SUMMARY_COLLECTION": "test_summary_articles",
                "AWS_S3_BUCKET_NAME": "test-news-bucket",
                "AWS_S3_NEWS_PREFIX": "news/",
                "ENABLE_NOTIFICATIONS": "true",
                "SLACK_WEBHOOK_URL": "https://mock-slack-webhook.com/test",
                "MS_TEAMS_WEBHOOK_URL": "https://mock-teams-webhook.com/test",
                "ALERT_EMAIL_RECIPIENTS": "test@example.com",
                "EMAIL_NOTIFICATION": "test@example.com"
            }
            return test_variables.get(key, default)
        
        mock_var_get.side_effect = variable_side_effect
        yield


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