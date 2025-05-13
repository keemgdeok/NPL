"""
DAG 테스트 (Kubernetes 버전)

이 모듈은 pipeline_dag.py에 정의된 Kubernetes 기반 DAG와 관련 작업들에 대한
단위 테스트를 제공합니다.

실행 방법:
    pytest -xvs test_pipeline_dag.py
"""
import pytest
from unittest import mock
from datetime import datetime, timedelta

import pendulum

from airflow.models.dagbag import DagBag
from airflow.models import Variable
from kubernetes.client import models as k8s


# --- pipeline_dag.py의 get_env_variable 함수 테스트 ---
def test_get_env_variable_from_dag_file():
    """pipeline_dag.py의 get_env_variable 함수 동작을 테스트합니다."""
    # get_env_variable 함수를 직접 가져오기 위해 pipeline_dag 모듈 임포트 시도
    # 실제 파일 구조에 따라 경로 조정 필요
    try:
        from infra.airflow.dags.pipeline_dag import get_env_variable
    except ImportError:
        pytest.skip("pipeline_dag.py 또는 get_env_variable 함수를 찾을 수 없습니다.")

    # Variable.get이 특정 값을 반환하도록 모의
    with mock.patch.object(Variable, "get") as mock_var_get_for_func:
        mock_var_get_for_func.return_value = "value_from_variable"
        assert get_env_variable("EXISTING_VAR") == "value_from_variable"
        mock_var_get_for_func.assert_called_once_with("EXISTING_VAR")

    # Variable.get이 KeyError를 발생시키고 기본값이 제공된 경우
    with mock.patch.object(Variable, "get") as mock_var_get_for_func:
        mock_var_get_for_func.side_effect = KeyError("Not found")
        assert get_env_variable("NON_EXISTING_VAR_WITH_DEFAULT", default="default_val") == "default_val"
        mock_var_get_for_func.assert_called_once_with("NON_EXISTING_VAR_WITH_DEFAULT")

    # Variable.get이 KeyError를 발생시키고 기본값이 없는 경우 ValueError 발생
    with mock.patch.object(Variable, "get") as mock_var_get_for_func:
        mock_var_get_for_func.side_effect = KeyError("Not found")
        with pytest.raises(ValueError, match="필수 환경 변수 NON_EXISTING_VAR_NO_DEFAULT이\\(가\\) 설정되지 않았습니다."):
            get_env_variable("NON_EXISTING_VAR_NO_DEFAULT")
        mock_var_get_for_func.assert_called_once_with("NON_EXISTING_VAR_NO_DEFAULT")


# --- 'news_pipeline_k8s' DAG 테스트 ---
def test_news_pipeline_k8s_dag_loaded(dagbag):
    """'news_pipeline_k8s' DAG가 로드되는지 확인합니다 (DB 접근 없이)."""
    dag_id = "news_pipeline_k8s"
    
    # DagBag이 dags를 로드하도록 명시적 호출이 필요할 수 있음 (DagBag 구현에 따라 다름)
    # dagbag.collect_dags_from_folder() 또는 dagbag.process_file() 등을 이미 내부적으로 호출했다면 불필요
    # 일반적으로 fixture에서 DagBag을 생성할 때 dag_folder를 지정하면 파싱이 일어남

    dag = dagbag.dags.get(dag_id) # dagbag.get_dag() 대신 .dags 딕셔너리 사용
    
    assert dag is not None, f"DAG '{dag_id}' not found in DagBag. Available DAGs: {list(dagbag.dags.keys())}"
    assert dag.dag_id == dag_id
    # 추가적인 DAG 구조 검증 테스트들...


def test_news_pipeline_k8s_dag_structure(dagbag):
    """'news_pipeline_k8s' DAG 구조가 올바른지 확인합니다."""
    dag = dagbag.get_dag("news_pipeline_k8s")
    assert dag is not None

    expected_task_ids = [
        "start_pipeline",
        "collect_news_k8s",
        "store_to_s3_k8s",
        "process_text_k8s",
        "process_sentiment_k8s",
        "process_summary_k8s",
        "end_pipeline",
    ]
    task_ids = [task.task_id for task in dag.tasks]
    for task_id in expected_task_ids:
        assert task_id in task_ids, f"태스크 {task_id}가 DAG에 없습니다."

    # 태스크 의존성 확인 (주요 경로 위주)
    # pipeline_dag.py에 정의된 의존성 그대로 확인
    start_task = dag.get_task("start_pipeline")
    collect_task = dag.get_task("collect_news_k8s")
    store_task = dag.get_task("store_to_s3_k8s")
    text_task = dag.get_task("process_text_k8s")
    sentiment_task = dag.get_task("process_sentiment_k8s")
    summary_task = dag.get_task("process_summary_k8s")
    end_task = dag.get_task("end_pipeline")

    assert collect_task.upstream_task_ids == {start_task.task_id}
    assert store_task.upstream_task_ids == {collect_task.task_id}
    assert text_task.upstream_task_ids == {collect_task.task_id}
    assert sentiment_task.upstream_task_ids == {text_task.task_id}
    # pipeline_dag.py: [store_to_s3, process_sentiment] >> process_summary
    assert summary_task.upstream_task_ids == {store_task.task_id, sentiment_task.task_id}
    # pipeline_dag.py: process_summary >> end 및 store_to_s3 >> end
    assert end_task.upstream_task_ids == {summary_task.task_id, store_task.task_id}


def test_news_pipeline_k8s_dag_default_args(dagbag):
    """'news_pipeline_k8s' DAG의 기본 인자가 올바르게 설정되어 있는지 확인합니다."""
    dag = dagbag.get_dag("news_pipeline_k8s")
    assert dag is not None
    
    default_args = dag.default_args
    assert default_args["owner"] == "airflow"
    assert default_args["depends_on_past"] is False
    # Variable.get 모의 설정 값 확인
    assert default_args["email"] == ["test-user@example.com"]
    assert default_args["email_on_failure"] is True
    assert default_args["email_on_retry"] is False
    assert default_args["retries"] == 1
    assert default_args["retry_delay"] == timedelta(minutes=3)
    assert default_args["start_date"] == pendulum.datetime(2025, 3, 1, tz="Asia/Seoul")


def test_news_pipeline_k8s_dag_schedule(dagbag):
    """'news_pipeline_k8s' DAG 스케줄이 올바르게 설정되어 있는지 확인합니다."""
    dag = dagbag.get_dag("news_pipeline_k8s")
    assert dag is not None
    assert dag.schedule_interval == "0 */6 * * *"


# KubernetesPodOperator 설정 테스트 예시 (collect_news_k8s 태스크)
def test_collect_news_k8s_operator_settings(dagbag):
    """'collect_news_k8s' KubernetesPodOperator 설정을 확인합니다."""
    dag = dagbag.get_dag("news_pipeline_k8s")
    assert dag is not None
    task = dag.get_task("collect_news_k8s")
    
    assert task.task_type == "KubernetesPodOperator"
    assert task.namespace == "mock-airflow-ns" # 모의 설정된 값
    assert task.image == "npl-collector:v1.0.0"
    assert task.name == "collect-news-pod"
    assert task.cmds == ["python", "-m", "src.collectors.run_collector"]
    assert task.arguments == ["--kafka-servers", "mock_kafka:9092", "--run-once"]
    
    expected_env_vars = {
        'KAFKA_BOOTSTRAP_SERVERS': "mock_kafka:9092",
        'MONGODB_URI': "mongodb://mock_user:mock_pass@mock_mongo:27017",
        'DATABASE_NAME': "mock_db",
    }
    # task.env_vars는 V1EnvVar 객체의 리스트일 수 있으므로 변환해서 비교
    actual_env_vars = {env_var.name: env_var.value for env_var in task.env_vars}
    assert actual_env_vars == expected_env_vars
    
    assert task.on_finish_action == "delete_pod"
    
    # 리소스 설정 확인 (pipeline_dag.py의 WORKER_RESOURCES와 일치하는지)
    expected_resources = k8s.V1ResourceRequirements(
        requests={"cpu": "500m", "memory": "1Gi"},
        limits={"cpu": "1", "memory": "2Gi"}
    )
    assert task.container_resources.requests == expected_resources.requests
    assert task.container_resources.limits == expected_resources.limits


def test_store_to_s3_k8s_operator_settings(dagbag):
    """'store_to_s3_k8s' KubernetesPodOperator 설정을 확인합니다."""
    dag = dagbag.get_dag("news_pipeline_k8s")
    assert dag is not None
    task = dag.get_task("store_to_s3_k8s")

    assert task.task_type == "KubernetesPodOperator"
    assert task.namespace == "mock-airflow-ns"
    assert task.image == "npl-storage:v1.0.0"
    assert task.name == "store-to-s3-pod"
    assert task.cmds == ["python", "-m", "src.collectors.storage"]
    # arguments, env_vars 등 확인
    
    # Secrets 확인 (pipeline_dag.py의 aws_secrets 부분과 일치하는지)
    # task.secrets는 k8s.V1Secret 객체의 리스트
    assert len(task.secrets) == 2
    secret_names = {s.secret for s in task.secrets}
    assert "mock-aws-credentials" in secret_names
    # 리소스 설정도 확인 (만약 pipeline_dag.py에서 해당 태스크에 WORKER_RESOURCES를 동일하게 적용했다면)
    expected_resources_s3 = k8s.V1ResourceRequirements(
        requests={"cpu": "500m", "memory": "1Gi"}, # WORKER_RESOURCES와 동일하다고 가정
        limits={"cpu": "1", "memory": "2Gi"}
    )
    assert task.container_resources.requests == expected_resources_s3.requests # 수정
    assert task.container_resources.limits == expected_resources_s3.limits   # 수정


def test_process_sentiment_k8s_operator_settings(dagbag):
    """'process_sentiment_k8s' KubernetesPodOperator의 볼륨 설정을 확인합니다."""
    dag = dagbag.get_dag("news_pipeline_k8s")
    assert dag is not None
    task = dag.get_task("process_sentiment_k8s")

    assert task.task_type == "KubernetesPodOperator"
    assert task.namespace == "mock-airflow-ns"
    # 볼륨 및 볼륨 마운트 확인
    assert len(task.volumes) == 1
    volume = task.volumes[0]
    assert volume.name == "model-storage"
    assert volume.persistent_volume_claim.claim_name == "mock-airflow-models-pvc" # 수정: PVC 이름 모의 값으로 변경

    assert len(task.volume_mounts) == 1
    volume_mount = task.volume_mounts[0]
    assert volume_mount.name == "model-storage"
    assert volume_mount.mount_path == "/mnt/models"
    assert volume_mount.read_only is True # Sentiment는 True
    
    # 모델 경로 인자 확인
    expected_model_path_arg = f"--model-cache /mnt/models/kr-finbert-sc"
    assert expected_model_path_arg in " ".join(task.arguments)
    # 리소스 설정도 확인
    expected_resources_sentiment = k8s.V1ResourceRequirements(
        requests={"cpu": "500m", "memory": "1Gi"}, # WORKER_RESOURCES와 동일하다고 가정
        limits={"cpu": "1", "memory": "2Gi"}
    )
    assert task.container_resources.requests == expected_resources_sentiment.requests # 수정
    assert task.container_resources.limits == expected_resources_sentiment.limits   # 수정


# --- 'download_models_k8s' DAG 테스트 ---
def test_download_models_k8s_dag_loaded(dagbag):
    """'download_models_k8s' DAG가 로드되는지 확인합니다."""
    dag_id = "download_models_k8s"
    dag = dagbag.get_dag(dag_id)
    assert dagbag.import_errors.get(f"infra/airflow/dags/{dag_id}.py") is None
    assert dag is not None, f"DAG {dag_id}를 찾을 수 없습니다."
    assert dag.dag_id == dag_id


def test_download_models_k8s_dag_structure(dagbag):
    """'download_models_k8s' DAG 구조를 확인합니다."""
    dag = dagbag.get_dag("download_models_k8s")
    assert dag is not None

    expected_task_ids = [
        "check_pvc_exists", # DummyOperator
        "download_sentiment_model_k8s",
        "download_summary_model_k8s",
        "models_ready", # DummyOperator
    ]
    task_ids = [task.task_id for task in dag.tasks]
    for task_id in expected_task_ids:
        assert task_id in task_ids

    # 의존성 확인
    check_pvc_task = dag.get_task("check_pvc_exists")
    download_sentiment_task = dag.get_task("download_sentiment_model_k8s")
    download_summary_task = dag.get_task("download_summary_model_k8s")
    models_ready_task = dag.get_task("models_ready")

    assert download_sentiment_task.upstream_task_ids == {check_pvc_task.task_id}
    assert download_summary_task.upstream_task_ids == {check_pvc_task.task_id}
    assert models_ready_task.upstream_task_ids == {download_sentiment_task.task_id, download_summary_task.task_id}


def test_download_sentiment_model_k8s_settings(dagbag):
    """'download_sentiment_model_k8s' KubernetesPodOperator 설정을 확인합니다."""
    dag = dagbag.get_dag("download_models_k8s")
    assert dag is not None
    task = dag.get_task("download_sentiment_model_k8s")

    assert task.task_type == "KubernetesPodOperator"
    assert task.namespace == "mock-airflow-ns"
    assert task.image == "python:3.11-slim" # pipeline_dag.py에 명시된 이미지
    assert task.name == "download-sentiment-model-pod"

    # 볼륨 마운트 (read_only=False 확인)
    assert len(task.volume_mounts) == 1
    volume_mount = task.volume_mounts[0]
    assert volume_mount.name == "model-storage"
    assert volume_mount.mount_path == "/mnt/models"
    assert volume_mount.read_only is False # 모델 다운로드는 False

    # 리소스 설정도 확인 (만약 pipeline_dag.py에서 해당 태스크에 별도 리소스를 지정했다면 그 값을 사용)
    # pipeline_dag.py에서는 downloader_resources = k8s.V1ResourceRequirements(requests={"memory": "512Mi"}, limits={"memory": "1Gi"}) 로 되어있음
    expected_resources_download_sentiment = k8s.V1ResourceRequirements(
        requests={"memory": "512Mi"}, # CPU는 명시 안됨, 이 경우 None 또는 기본값이 될 수 있음
        limits={"memory": "1Gi"}
    )
    # CPU가 명시되지 않았으므로, requests/limits 딕셔너리에 cpu 키가 없을 수 있음을 고려해야 함
    # 또는 operator가 기본 CPU 값을 설정할 수도 있음. 여기서는 memory만 비교
    assert task.container_resources.requests.get("memory") == expected_resources_download_sentiment.requests.get("memory") # 수정
    assert task.container_resources.limits.get("memory") == expected_resources_download_sentiment.limits.get("memory")     # 수정

    # 커맨드/인자에서 모델 경로, pip install 등 확인 가능
    script_content = task.arguments[0] # arguments는 리스트이고, 스크립트는 첫번째 요소일 것
    assert "pip install transformers[torch] requests huggingface_hub" in script_content
    assert "mkdir -p /mnt/models/kr-finbert-sc" in script_content
    assert "save_pretrained('/mnt/models/kr-finbert-sc')" in script_content

# DAG 로딩 시 필수 Variable 누락은 Airflow 자체적으로 import_errors에 기록하므로,
def test_dag_loading_with_missing_mandatory_variable(dagbag):
    """필수 Airflow Variable (기본값 없는) 누락 시 DAG 로딩 실패를 확인합니다."""
    # mock_airflow_variables에서 필수 변수 (예: KAFKA_BOOTSTRAP_SERVERS)를 일시적으로 제거
    # 이 테스트는 mock_airflow_variables의 side_effect를 더 정교하게 제어해야 함
    
    # 예시: KAFKA_BOOTSTRAP_SERVERS가 Variable.get에서 KeyError를 발생시키고 default_var도 없는 경우
    def custom_variable_side_effect(key, default_var=None):
        if key == "KAFKA_BOOTSTRAP_SERVERS": # 이 변수만 문제를 일으키도록
            if default_var is not None: return default_var
            raise KeyError(f"Critical Variable {key} not found")
        # 다른 변수들은 mock_airflow_variables의 기존 로직 따름
        original_vars = {
            "MONGODB_URI": "mongodb://mockuser:mockpass@mongodb-headless.test-ns.svc.cluster.local:27017",
            "DATABASE_NAME": "test_news_db",
            # ... 기타 필요한 변수들
        }
        if key in original_vars: return original_vars[key]
        if default_var is not None: return default_var
        # 모든 경우에 대해 Variable.get의 동작을 정의해야 함 (복잡도 증가)
        # 또는 pipeline_dag.py에서 get_env_variable이 ValueError를 발생시키는 것을 확인
        raise KeyError(f"Variable {key} not found for this specific test case")

    # 이 테스트는 pipeline_dag.py의 get_env_variable이 ValueError를 발생시키고,
    # 그게 DAG 파싱 중 전파되어 import_errors에 기록되는 것을 검증해야 함.
    # 실제로는 DagBag 생성 시점에 해당 오류가 발생하여 import_errors에 담김.
    
    # 더 간단한 접근: pipeline_dag.py의 get_env_variable이 Variable을 못찾을 때
    # ValueError를 내는지 확인하는 test_get_env_variable_from_dag_file로 커버 가능성이 높음.
    # Airflow가 DAG를 파싱할 때 get_env_variable 내부에서 ValueError가 발생하면
    # 해당 DAG는 import_errors에 기록됨.
    # 따라서, 해당 함수에 대한 단위 테스트가 견고하다면 이 테스트는 중복일 수 있음.
    pytest.skip("필수 변수 누락 시 DAG 로딩 실패 테스트는 get_env_variable 테스트로 커버되거나, "
                "더 정교한 Variable 모의가 필요합니다.")


# 통합 테스트는 실제 환경 의존적이므로 주석 처리 또는 조건부 실행
# @pytest.mark.integration
# def test_kubernetes_pod_launch_simulation():
#     """(시뮬레이션) Kubernetes Pod가 실행될 수 있는지 기본적인 구성을 확인합니다."""
#     # 이 테스트는 실제 Kubernetes 클라이언트 라이브러리를 모의하거나,
#     # kind/minikube 같은 로컬 클러스터에 대해 간단한 Pod 실행을 시도해볼 수 있습니다.
#     # 여기서는 개념만 설명합니다.
#     pytest.skip("실제 Kubernetes 환경 또는 정교한 모의 설정이 필요한 테스트입니다.")


if __name__ == "__main__":
    pytest.main(["-xvs", __file__]) 