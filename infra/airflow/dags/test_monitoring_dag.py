"""
뉴스 모니터링 DAG 테스트

이 모듈은 monitoring_dag.py에 정의된 DAG와 관련 작업 함수들에 대한 
단위 테스트를 제공합니다.

실행 방법:
    pytest -xvs test_monitoring_dag.py
"""
import os
import sys
import json
import pytest
from unittest import mock
from datetime import datetime, timedelta

from airflow.models import DagBag, Variable, Connection, DagRun
from airflow.utils.session import create_session
from airflow.utils.db import provide_session


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
        "SLACK_WEBHOOK_URL": "https://mock-slack-webhook.com/test",
        "MS_TEAMS_WEBHOOK_URL": "https://mock-teams-webhook.com/test",
        "ALERT_EMAIL_RECIPIENTS": "test@example.com"
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
                "ENABLE_NOTIFICATIONS": "true",
                "SLACK_WEBHOOK_URL": "https://mock-slack-webhook.com/test",
                "MS_TEAMS_WEBHOOK_URL": "https://mock-teams-webhook.com/test",
                "ALERT_EMAIL_RECIPIENTS": "test@example.com",
                "EMAIL_NOTIFICATION": "test@example.com"
            }
            return test_variables.get(key, default)
        
        mock_var_get.side_effect = variable_side_effect
        yield


# 테스트: DAG 존재 확인
def test_dag_loaded(dagbag):
    """'news_monitoring' DAG가 로드되는지 확인합니다."""
    dag = dagbag.get_dag("news_monitoring")
    assert dagbag.import_errors == {}
    assert dag is not None
    assert len(dag.tasks) > 0


# 테스트: DAG 구조 확인
def test_dag_structure(dagbag):
    """DAG 구조가 올바른지 확인합니다."""
    dag = dagbag.get_dag("news_monitoring")
    
    # 필수 태스크 존재 확인
    task_ids = [task.task_id for task in dag.tasks]
    expected_task_ids = [
        "start_monitoring",
        "check_mongodb_status",
        "check_kafka_status",
        "check_pipeline_status",
        "generate_monitoring_report"
    ]
    
    for task_id in expected_task_ids:
        assert task_id in task_ids
    
    # 태스크 의존성 확인
    start_task = dag.get_task("start_monitoring")
    mongodb_task = dag.get_task("check_mongodb_status")
    kafka_task = dag.get_task("check_kafka_status")
    pipeline_task = dag.get_task("check_pipeline_status")
    report_task = dag.get_task("generate_monitoring_report")
    
    # 주요 의존성 확인
    assert mongodb_task.upstream_task_ids == {"start_monitoring"}
    assert kafka_task.upstream_task_ids == {"start_monitoring"}
    assert pipeline_task.upstream_task_ids == {"start_monitoring"}
    assert report_task.upstream_task_ids.issuperset({"check_mongodb_status", "check_kafka_status", "check_pipeline_status"})


# 테스트: DAG 기본 인자 확인
def test_dag_default_args(dagbag):
    """DAG의 기본 인자가 올바르게 설정되어 있는지 확인합니다."""
    dag = dagbag.get_dag("news_monitoring")
    
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
    dag = dagbag.get_dag("news_monitoring")
    assert dag.schedule_interval == "0 */2 * * *"  # 2시간마다 실행


# MongoDB 상태 체크 함수 테스트
@mock.patch("pymongo.MongoClient")
def test_check_mongodb_status(mock_mongo):
    """MongoDB 상태 체크 함수를 테스트합니다."""
    # 모듈 가져오기 시도
    sys.path.append("/opt/airflow/dags")
    
    try:
        # monitoring_dag.py에서 함수 임포트 시도
        from monitoring_dag import check_mongodb_status
        
        # MongoDB 모의 설정
        mock_db = mock_mongo.return_value.__getitem__.return_value
        mock_db.command.return_value = {"ok": 1}
        mock_db.list_collection_names.return_value = [
            "test_news_articles", "test_processed_articles", 
            "test_sentiment_articles", "test_summary_articles"
        ]
        
        mock_collection = mock_db.__getitem__.return_value
        mock_collection.count_documents.return_value = 100
        
        # 함수 실행
        result = check_mongodb_status()
        
        # 결과 검증
        assert result is not None
        assert "status" in result
        assert result["status"] == "success"
        assert "collections" in result
        assert len(result["collections"]) > 0
        assert "collection_counts" in result
        
    except ImportError:
        pytest.skip("check_mongodb_status 함수를 가져올 수 없습니다.")


# Kafka 상태 체크 함수 테스트
@mock.patch("kafka.KafkaConsumer")
def test_check_kafka_status(mock_kafka):
    """Kafka 상태 체크 함수를 테스트합니다."""
    sys.path.append("/opt/airflow/dags")
    
    try:
        from monitoring_dag import check_kafka_status
        
        # Kafka 모의 설정
        mock_kafka.return_value.topics.return_value = set([
            "news-collected", "news-processed", "news-sentiment", "news-summary"
        ])
        
        # 함수 실행
        result = check_kafka_status()
        
        # 결과 검증
        assert result is not None
        assert "status" in result
        assert result["status"] == "success"
        assert "topics" in result
        assert len(result["topics"]) > 0
        
    except ImportError:
        pytest.skip("check_kafka_status 함수를 가져올 수 없습니다.")


# 파이프라인 상태 체크 함수 테스트
@provide_session
@mock.patch("airflow.models.DagRun")
def test_check_pipeline_status(mock_dag_run, session=None):
    """파이프라인 상태 체크 함수를 테스트합니다."""
    sys.path.append("/opt/airflow/dags")
    
    try:
        from monitoring_dag import check_pipeline_status
        
        # DagRun 모의 설정
        mock_dag_run_obj = mock.MagicMock()
        mock_dag_run_obj.state = "success"
        mock_dag_run_obj.execution_date = datetime.now() - timedelta(hours=5)
        mock_dag_run.find.return_value = [mock_dag_run_obj]
        
        # 함수 실행
        result = check_pipeline_status()
        
        # 결과 검증
        assert result is not None
        assert "status" in result
        assert result["status"] in ["success", "warning", "error"]
        assert "last_run_state" in result
        assert "last_run_time" in result
        
    except ImportError:
        pytest.skip("check_pipeline_status 함수를 가져올 수 없습니다.")


# 모니터링 보고서 생성 함수 테스트
@mock.patch("requests.post")
def test_generate_monitoring_report(mock_requests):
    """모니터링 보고서 생성 함수를 테스트합니다."""
    sys.path.append("/opt/airflow/dags")
    
    try:
        from monitoring_dag import generate_monitoring_report, send_notification
        
        # HTTP 요청 모의 설정
        mock_requests.return_value.status_code = 200
        mock_requests.return_value.text = "OK"
        
        # 컨텍스트 모의 설정
        context = {
            "task_instance": mock.MagicMock()
        }
        context["task_instance"].xcom_pull.side_effect = lambda task_ids: {
            "check_mongodb_status": {
                "status": "success",
                "collections": ["test_news_articles", "test_processed_articles"],
                "collection_counts": {"test_news_articles": 100}
            },
            "check_kafka_status": {
                "status": "success",
                "topics": ["news-collected", "news-processed"]
            },
            "check_pipeline_status": {
                "status": "success",
                "last_run_state": "success",
                "last_run_time": datetime.now().isoformat()
            }
        }.get(task_ids)
        
        # 함수 실행
        result = generate_monitoring_report(**context)
        
        # 결과 검증
        assert result is not None
        assert isinstance(result, dict)
        assert "overall_status" in result
        assert result["overall_status"] in ["success", "warning", "error"]
        assert "timestamp" in result
        assert "components" in result
        assert len(result["components"]) > 0
        
    except ImportError:
        pytest.skip("generate_monitoring_report 함수를 가져올 수 없습니다.")


# 알림 전송 함수 테스트
@mock.patch("requests.post")
@mock.patch("airflow.utils.email.send_email")
def test_send_notification(mock_email, mock_requests):
    """알림 전송 함수를 테스트합니다."""
    sys.path.append("/opt/airflow/dags")
    
    try:
        from monitoring_dag import send_notification
        
        # HTTP 요청 모의 설정
        mock_requests.return_value.status_code = 200
        mock_requests.return_value.text = "OK"
        
        # 이메일 전송 모의 설정
        mock_email.return_value = True
        
        # 함수 실행
        details = {"component": "mongodb", "error": "연결 실패"}
        result = send_notification("error", "MongoDB 연결 오류", details)
        
        # 결과 검증
        assert result is True
        # Slack 알림 확인
        assert mock_requests.called
        # 오류 수준일 때 이메일 전송 확인
        assert mock_email.called
        
    except ImportError:
        pytest.skip("send_notification 함수를 가져올 수 없습니다.")


# 테스트: 패키지 설치 체크 함수
@mock.patch("subprocess.check_call")
@mock.patch("importlib.util.find_spec")
def test_check_and_install_packages(mock_find_spec, mock_subprocess):
    """패키지 설치 체크 함수를 테스트합니다."""
    sys.path.append("/opt/airflow/dags")
    
    try:
        from monitoring_dag import check_and_install_packages, REQUIRED_PACKAGES
        
        # find_spec이 None을 반환하도록 설정 (패키지 없음)
        mock_find_spec.return_value = None
        
        # 함수 실행
        check_and_install_packages()
        
        # 패키지 설치 호출 확인
        assert mock_subprocess.called
        called_args = mock_subprocess.call_args[0][0]
        assert sys.executable in called_args
        assert "pip" in called_args
        assert "install" in called_args
        
    except ImportError:
        pytest.skip("check_and_install_packages 함수를 가져올 수 없습니다.")


# 테스트: 컬렉션 확인 기능
def test_verify_collections():
    """MongoDB 컬렉션 확인 기능을 테스트합니다."""
    sys.path.append("/opt/airflow/dags")
    
    try:
        from monitoring_dag import get_mongodb_collections
        
        # 함수 실행
        collections = get_mongodb_collections()
        
        # 결과 검증
        assert collections is not None
        assert isinstance(collections, dict)
        assert "news" in collections
        assert "processed" in collections
        assert "sentiment" in collections
        assert "summary" in collections
        
    except ImportError:
        pytest.skip("get_mongodb_collections 함수를 가져올 수 없습니다.")


if __name__ == "__main__":
    pytest.main(["-xvs", __file__]) 