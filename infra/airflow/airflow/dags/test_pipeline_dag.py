"""
뉴스 파이프라인 DAG 테스트

이 모듈은 pipeline_dag.py에 정의된 DAG와 관련 작업 함수들에 대한 
단위 테스트를 제공합니다.

실행 방법:
    pytest -xvs test_pipeline_dag.py
"""
import os
import pytest
from unittest import mock
from datetime import datetime, timedelta

from airflow.models import DagBag, Variable, Connection
from airflow.utils.session import create_session


# 테스트 환경 설정
@pytest.fixture
def dagbag():
    """테스트용 DagBag 객체를 반환합니다."""
    return DagBag(dag_folder="/opt/airflow/dags", include_examples=False)


# 필수 환경 변수 모의 설정
@pytest.fixture(autouse=True)
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
        "AWS_S3_BUCKET_NAME": "test-news-bucket"
    }):
        yield


# Airflow 변수 모의 설정
@pytest.fixture(autouse=True)
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
                "EMAIL_NOTIFICATION": "test@example.com"
            }
            return test_variables.get(key, default)
        
        mock_var_get.side_effect = variable_side_effect
        yield


# 테스트: DAG 존재 확인
def test_dag_loaded(dagbag):
    """'news_pipeline' DAG가 로드되는지 확인합니다."""
    dag = dagbag.get_dag("news_pipeline")
    assert dagbag.import_errors == {}
    assert dag is not None
    assert len(dag.tasks) > 0


# 테스트: DAG 구조 확인
def test_dag_structure(dagbag):
    """DAG 구조가 올바른지 확인합니다."""
    dag = dagbag.get_dag("news_pipeline")
    
    # 필수 태스크 존재 확인
    task_ids = [task.task_id for task in dag.tasks]
    expected_task_ids = [
        "start_pipeline", 
        "collect_news", 
        "store_to_s3", 
        "process_text", 
        "process_sentiment", 
        "process_summary", 
        "end_pipeline"
    ]
    
    for task_id in expected_task_ids:
        assert task_id in task_ids
    
    # 태스크 의존성 확인
    start_task = dag.get_task("start_pipeline")
    collect_task = dag.get_task("collect_news")
    store_task = dag.get_task("store_to_s3")
    text_task = dag.get_task("process_text")
    sentiment_task = dag.get_task("process_sentiment")
    summary_task = dag.get_task("process_summary")
    end_task = dag.get_task("end_pipeline")
    
    # 주요 의존성 확인
    assert collect_task.upstream_task_ids == {"start_pipeline"}
    assert store_task.upstream_task_ids == {"collect_news"}
    assert text_task.upstream_task_ids == {"collect_news"}
    assert sentiment_task.upstream_task_ids == {"process_text"}
    assert summary_task.upstream_task_ids == {"process_text"}
    assert end_task.upstream_task_ids.issuperset({"process_sentiment", "process_summary"})


# 테스트: DAG 기본 인자 확인
def test_dag_default_args(dagbag):
    """DAG의 기본 인자가 올바르게 설정되어 있는지 확인합니다."""
    dag = dagbag.get_dag("news_pipeline")
    
    default_args = dag.default_args
    assert default_args["owner"] == "airflow"
    assert default_args["depends_on_past"] is False
    assert default_args["email_on_failure"] is True
    assert default_args["email_on_retry"] is False
    assert isinstance(default_args["retry_delay"], timedelta)
    assert default_args["retries"] > 0


# 테스트: DAG 스케줄 확인
def test_dag_schedule(dagbag):
    """DAG 스케줄이 올바르게 설정되어 있는지 확인합니다."""
    dag = dagbag.get_dag("news_pipeline")
    assert dag.schedule_interval == "0 */6 * * *"  # 6시간마다 실행


# 모의 작업 함수 테스트
@mock.patch("pymongo.MongoClient")
@mock.patch("kafka.KafkaProducer")
def test_collect_news_function(mock_kafka, mock_mongo, dagbag):
    """뉴스 수집 함수의 동작을 테스트합니다."""
    # 필요한 경우 모듈 가져오기
    import sys
    sys.path.append("/opt/airflow/dags")
    
    try:
        # 이 부분은 실제 collect_news 함수가 별도의 모듈로 존재하는 경우에만 필요합니다
        # from pipeline_dag import collect_news
        
        # 모의 MongoDB 클라이언트 설정
        mock_db = mock_mongo.return_value.__getitem__.return_value
        mock_collection = mock_db.__getitem__.return_value
        mock_collection.insert_many.return_value = mock.MagicMock()
        
        # 모의 Kafka 프로듀서 설정
        mock_kafka.return_value.send.return_value = mock.MagicMock()
        
        # collect_news 함수가 별도의 모듈이 아닌 경우, 여기서 테스트 내용 조정 필요
        # 예시: collect_news 함수가 정의되어 있는지 확인
        dag = dagbag.get_dag("news_pipeline")
        collect_task = dag.get_task("collect_news")
        assert collect_task is not None
        
    except ImportError:
        # 모듈을 가져올 수 없는 경우, 테스트 건너뛰기
        pytest.skip("collect_news 함수를 가져올 수 없습니다. 이 테스트를 실행하려면 함수가 올바르게 정의되어 있는지 확인하세요.")


# 오류 처리 테스트 (환경 변수 누락 시)
def test_missing_variables_handling():
    """필수 환경 변수가 누락된 경우의 오류 처리를 테스트합니다."""
    with mock.patch.object(Variable, "get") as mock_var_get:
        # Variable.get이 키가 없을 때 KeyError를 발생시키도록 설정
        mock_var_get.side_effect = KeyError("환경 변수를 찾을 수 없습니다")
        
        # 새 DagBag을 로드할 때 오류가 발생할 것으로 예상
        new_dagbag = DagBag(dag_folder="/opt/airflow/dags", include_examples=False)
        
        # 예상되는 동작: DAG 로딩에 실패하거나 오류가 기록됨
        # 이 테스트는 환경 변수 오류를 처리하는 방식에 따라 조정 필요
        assert new_dagbag.import_errors
        
        # 또는 DAG가 로드되지만 실행 중 오류가 발생하는 경우 테스트
        # (이는 DAG가 실제로 어떻게 구현되었는지에 따라 다를 수 있음)


# 통합 테스트 (Docker 실행 테스트)
@pytest.mark.integration
def test_docker_services_initialization():
    """Docker 서비스 초기화 기능을 테스트합니다."""
    # 이 테스트는 실제 Docker를 사용하므로 integration 마커로 표시
    # pytest -xvs test_pipeline_dag.py -m integration
    pytest.skip("실제 Docker 환경이 필요한 테스트입니다. 개발 환경에서만 실행하세요.")
    
    # Docker Python SDK를 사용한 테스트 코드
    # import docker
    # client = docker.from_env()
    # ...


if __name__ == "__main__":
    pytest.main(["-xvs", __file__]) 