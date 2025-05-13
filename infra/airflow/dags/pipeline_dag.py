from __future__ import annotations

import pendulum
from datetime import timedelta
from typing import Dict, List, Optional, Any
from airflow.models.dag import DAG
from airflow.providers.cncf.kubernetes.operators.pod import KubernetesPodOperator
from airflow.operators.empty import EmptyOperator
from airflow.models import Variable
from airflow.providers.cncf.kubernetes.secret import Secret
from airflow.operators.python import PythonOperator
from kubernetes.client import models as k8s
from airflow.exceptions import AirflowFailException
from kubernetes import client, config
import logging

# =============================
# 환경별 분리 (예시)
# =============================
ENVIRONMENT = Variable.get("ENVIRONMENT", default_var="dev")  # dev, prod 등
VAR_PREFIX = f"airflow_dags_{ENVIRONMENT}_"

# --- Airflow Variable 이름 상수 정의 ---
VAR_EMAIL_NOTIFICATION = f"{VAR_PREFIX}email_notification"
VAR_K8S_NAMESPACE = f"{VAR_PREFIX}k8s_namespace"
VAR_MODEL_MOUNT_PATH = f"{VAR_PREFIX}model_mount_path"
VAR_MODEL_PVC_NAME = f"{VAR_PREFIX}model_pvc_name"
VAR_KAFKA_BOOTSTRAP_SERVERS = f"{VAR_PREFIX}kafka_bootstrap_servers"
VAR_MONGODB_URI = f"{VAR_PREFIX}mongodb_uri"
VAR_DATABASE_NAME = f"{VAR_PREFIX}database_name"
VAR_AWS_REGION = f"{VAR_PREFIX}aws_region"
VAR_S3_BUCKET_NAME = f"{VAR_PREFIX}s3_bucket_name"
VAR_AWS_K8S_SECRET_NAME = f"{VAR_PREFIX}aws_k8s_secret_name"
VAR_AWS_ACCESS_KEY_ID_SECRET_KEY = f"{VAR_PREFIX}aws_access_key_id_secret_key"
VAR_AWS_SECRET_ACCESS_KEY_SECRET_KEY = f"{VAR_PREFIX}aws_secret_access_key_secret_key"
VAR_COLLECTOR_IMAGE = f"{VAR_PREFIX}collector_image"
VAR_STORAGE_IMAGE = f"{VAR_PREFIX}storage_image"
VAR_TEXT_PROCESSOR_IMAGE = f"{VAR_PREFIX}text_processor_image"
VAR_SENTIMENT_PROCESSOR_IMAGE = f"{VAR_PREFIX}sentiment_processor_image"
VAR_SUMMARY_PROCESSOR_IMAGE = f"{VAR_PREFIX}summary_processor_image"
VAR_MODEL_DOWNLOADER_IMAGE = f"{VAR_PREFIX}model_downloader_image"
VAR_STORAGE_WAIT_EMPTY_SECONDS = f"{VAR_PREFIX}storage_wait_empty_seconds"
VAR_STORAGE_BATCH_SIZE = f"{VAR_PREFIX}storage_batch_size"
VAR_STORAGE_FLUSH_INTERVAL = f"{VAR_PREFIX}storage_flush_interval"
VAR_STORAGE_MAX_WORKERS = f"{VAR_PREFIX}storage_max_workers"
VAR_TEXT_PROCESSOR_MODE = f"{VAR_PREFIX}text_processor_mode"
VAR_SENTIMENT_PROCESSOR_MODE = f"{VAR_PREFIX}sentiment_processor_mode"
VAR_SUMMARY_PROCESSOR_MODE = f"{VAR_PREFIX}summary_processor_mode"
VAR_SENTIMENT_MODEL_NAME = f"{VAR_PREFIX}sentiment_model_name"
VAR_SENTIMENT_MODEL_HF_ID = f"{VAR_PREFIX}sentiment_model_hf_id"
VAR_SUMMARY_MODEL_NAME = f"{VAR_PREFIX}summary_model_name"
VAR_SUMMARY_MODEL_HF_ID = f"{VAR_PREFIX}summary_model_hf_id"
VAR_WORKER_REQUEST_CPU = f"{VAR_PREFIX}worker_request_cpu"
VAR_WORKER_REQUEST_MEMORY = f"{VAR_PREFIX}worker_request_memory"
VAR_WORKER_LIMIT_CPU = f"{VAR_PREFIX}worker_limit_cpu"
VAR_WORKER_LIMIT_MEMORY = f"{VAR_PREFIX}worker_limit_memory"
VAR_DOWNLOADER_REQUEST_MEMORY_SENTIMENT = f"{VAR_PREFIX}downloader_request_memory_sentiment"
VAR_DOWNLOADER_LIMIT_MEMORY_SENTIMENT = f"{VAR_PREFIX}downloader_limit_memory_sentiment"
VAR_DOWNLOADER_REQUEST_MEMORY_SUMMARY = f"{VAR_PREFIX}downloader_request_memory_summary"
VAR_DOWNLOADER_LIMIT_MEMORY_SUMMARY = f"{VAR_PREFIX}downloader_limit_memory_summary"
VAR_COLLECTOR_TIMEOUT = f"{VAR_PREFIX}collector_timeout"
VAR_STORAGE_TIMEOUT = f"{VAR_PREFIX}storage_timeout"
VAR_TEXT_PROCESSOR_TIMEOUT = f"{VAR_PREFIX}text_processor_timeout"
VAR_SENTIMENT_PROCESSOR_TIMEOUT = f"{VAR_PREFIX}sentiment_processor_timeout"
VAR_SUMMARY_PROCESSOR_TIMEOUT = f"{VAR_PREFIX}summary_processor_timeout"
VAR_DOWNLOAD_SENTIMENT_TIMEOUT = f"{VAR_PREFIX}download_sentiment_timeout"
VAR_DOWNLOAD_SUMMARY_TIMEOUT = f"{VAR_PREFIX}download_summary_timeout"

# =============================
# Helper Functions
# =============================
def get_airflow_variable(name: str, default: Optional[str] = None) -> str:
    """Airflow Variable을 가져오고 없는 경우 기본값 반환 또는 에러 발생

    Args:
        name (str): Variable 이름
        default (Optional[str]): 기본값
    Returns:
        str: Variable 값
    Raises:
        ValueError: 필수 Variable이 없을 때
    """
    return Variable.get(name, default_var=default)

def create_resource_requirements(request_cpu: str, request_mem: str, limit_cpu: str, limit_mem: str) -> k8s.V1ResourceRequirements:
    """KubernetesPodOperator에 사용할 리소스 객체 생성

    Args:
        request_cpu (str): 요청 CPU
        request_mem (str): 요청 메모리
        limit_cpu (str): 제한 CPU
        limit_mem (str): 제한 메모리
    Returns:
        k8s.V1ResourceRequirements: 리소스 객체
    """
    return k8s.V1ResourceRequirements(
        requests={"cpu": request_cpu, "memory": request_mem},
        limits={"cpu": limit_cpu, "memory": limit_mem}
    )

def create_memory_resource_requirements(request_mem: str, limit_mem: str) -> k8s.V1ResourceRequirements:
    """메모리만 제한하는 리소스 객체 생성

    Args:
        request_mem (str): 요청 메모리
        limit_mem (str): 제한 메모리
    Returns:
        k8s.V1ResourceRequirements: 리소스 객체
    """
    return k8s.V1ResourceRequirements(
        requests={"memory": request_mem},
        limits={"memory": limit_mem}
    )

def check_pvc_exists(pvc_name: str, namespace: str) -> None:
    """PVC가 존재하지 않으면 AirflowFailException 발생 및 로깅

    Args:
        pvc_name (str): PVC 이름
        namespace (str): 네임스페이스
    Raises:
        AirflowFailException: PVC가 없을 때
    """
    logger = logging.getLogger("airflow.task")
    try:
        config.load_incluster_config()
    except Exception:
        config.load_kube_config()
    v1 = client.CoreV1Api()
    pvcs = v1.list_namespaced_persistent_volume_claim(namespace=namespace)
    if not any(pvc.metadata.name == pvc_name for pvc in pvcs.items):
        logger.error(f"PVC '{pvc_name}'가 네임스페이스 '{namespace}'에 존재하지 않습니다.")
        raise AirflowFailException(f"PVC '{pvc_name}'가 네임스페이스 '{namespace}'에 존재하지 않습니다.")
    logger.info(f"PVC '{pvc_name}'가 네임스페이스 '{namespace}'에 존재함을 확인.")

# =============================
# Variable 값 및 리소스 객체 미리 로드
# =============================
k8s_namespace: str = get_airflow_variable(VAR_K8S_NAMESPACE, "airflow")
model_mount_path: str = get_airflow_variable(VAR_MODEL_MOUNT_PATH, "/mnt/models")
model_pvc_name: str = get_airflow_variable(VAR_MODEL_PVC_NAME, "airflow-models-pvc")
kafka_bootstrap_servers: str = get_airflow_variable(VAR_KAFKA_BOOTSTRAP_SERVERS)
mongodb_uri: str = get_airflow_variable(VAR_MONGODB_URI)
database_name: str = get_airflow_variable(VAR_DATABASE_NAME, "news_db")
aws_region: str = get_airflow_variable(VAR_AWS_REGION, "ap-northeast-2")
s3_bucket_name: str = get_airflow_variable(VAR_S3_BUCKET_NAME)
aws_k8s_secret_name: str = get_airflow_variable(VAR_AWS_K8S_SECRET_NAME, "aws-credentials")
aws_access_key_id_secret_key: str = get_airflow_variable(VAR_AWS_ACCESS_KEY_ID_SECRET_KEY, "aws_access_key_id")
aws_secret_access_key_secret_key: str = get_airflow_variable(VAR_AWS_SECRET_ACCESS_KEY_SECRET_KEY, "aws_secret_access_key")

worker_resources: k8s.V1ResourceRequirements = create_resource_requirements(
    get_airflow_variable(VAR_WORKER_REQUEST_CPU, "500m"),
    get_airflow_variable(VAR_WORKER_REQUEST_MEMORY, "1Gi"),
    get_airflow_variable(VAR_WORKER_LIMIT_CPU, "1"),
    get_airflow_variable(VAR_WORKER_LIMIT_MEMORY, "2Gi")
)
downloader_resources_sentiment: k8s.V1ResourceRequirements = create_memory_resource_requirements(
    get_airflow_variable(VAR_DOWNLOADER_REQUEST_MEMORY_SENTIMENT, "512Mi"),
    get_airflow_variable(VAR_DOWNLOADER_LIMIT_MEMORY_SENTIMENT, "1Gi")
)
downloader_resources_summary: k8s.V1ResourceRequirements = create_memory_resource_requirements(
    get_airflow_variable(VAR_DOWNLOADER_REQUEST_MEMORY_SUMMARY, "1Gi"),
    get_airflow_variable(VAR_DOWNLOADER_LIMIT_MEMORY_SUMMARY, "2Gi")
)

sentiment_model_name: str = get_airflow_variable(VAR_SENTIMENT_MODEL_NAME, 'kr-finbert-sc')
sentiment_model_hf_id: str = get_airflow_variable(VAR_SENTIMENT_MODEL_HF_ID, 'snunlp/KR-FinBert-SC')
sentiment_model_path: str = f"{model_mount_path}/{sentiment_model_name}"
summary_model_name: str = get_airflow_variable(VAR_SUMMARY_MODEL_NAME, 'kobart-summarization-model')
summary_model_hf_id: str = get_airflow_variable(VAR_SUMMARY_MODEL_HF_ID, 't5-base-korean-summarization')
summary_model_path: str = f"{model_mount_path}/{summary_model_name}"

# --- 공통 볼륨 및 마운트 ---
model_volume = k8s.V1Volume(
    name='model-storage',
    persistent_volume_claim=k8s.V1PersistentVolumeClaimVolumeSource(claim_name=model_pvc_name)
)
model_volume_mount_read_only = k8s.V1VolumeMount(
    name='model-storage',
    mount_path=model_mount_path,
    read_only=True
)
model_volume_mount_read_write = k8s.V1VolumeMount(
    name='model-storage',
    mount_path=model_mount_path,
    read_only=False
)

aws_secrets = [
    Secret(
        deploy_type="env",
        deploy_target="AWS_ACCESS_KEY_ID",
        secret=aws_k8s_secret_name,
        key=aws_access_key_id_secret_key
    ),
    Secret(
        deploy_type="env",
        deploy_target="AWS_SECRET_ACCESS_KEY",
        secret=aws_k8s_secret_name,
        key=aws_secret_access_key_secret_key
    )
]

# =============================
# KubernetesPodOperator 래퍼 함수 (공통 파라미터 적용)
# =============================
def k8s_pod_operator(
    task_id: str,
    image: str,
    cmds: list[str],
    arguments: list[str],
    env_vars: Optional[Dict[str, Any]] = None,
    volumes: Optional[list[Any]] = None,
    volume_mounts: Optional[list[Any]] = None,
    secrets: Optional[list[Any]] = None,
    container_resources: Optional[Any] = None,
    startup_timeout_seconds: Optional[int] = None,
    trigger_rule: Optional[str] = None,
) -> KubernetesPodOperator:
    """공통 파라미터가 적용된 KubernetesPodOperator 생성 래퍼

    Args:
        task_id (str): 태스크 ID
        image (str): 컨테이너 이미지
        cmds (list[str]): 실행 명령어
        arguments (list[str]): 인자
        env_vars (Optional[Dict[str, Any]]): 환경 변수
        volumes (Optional[list[Any]]): 볼륨
        volume_mounts (Optional[list[Any]]): 볼륨 마운트
        secrets (Optional[list[Any]]): 시크릿
        container_resources (Optional[Any]): 리소스
        startup_timeout_seconds (Optional[int]): 타임아웃
        trigger_rule (Optional[str]): 트리거 규칙
    Returns:
        KubernetesPodOperator: 생성된 오퍼레이터
    """
    return KubernetesPodOperator(
        task_id=task_id,
        namespace=k8s_namespace,
        image=image,
        cmds=cmds,
        arguments=arguments,
        env_vars=env_vars,
        volumes=volumes,
        volume_mounts=volume_mounts,
        secrets=secrets,
        get_logs=True,
        on_finish_action="delete_pod",
        container_resources=container_resources,
        startup_timeout_seconds=startup_timeout_seconds,
        trigger_rule=trigger_rule,
    )

# =============================
# 기본 인자 정의
# =============================
default_args = {
    'owner': 'airflow',
    'depends_on_past': False,
    'start_date': pendulum.datetime(2025, 3, 1, tz="Asia/Seoul"),
    'email': [get_airflow_variable(VAR_EMAIL_NOTIFICATION, 'alert@example.com')],
    'email_on_failure': True,
    'email_on_retry': False,
    'retries': 1,
    'retry_delay': timedelta(minutes=3),
}

# ==========================================
# === News Pipeline DAG 정의 ============
# ==========================================
with DAG(
    dag_id=f'news_pipeline_k8s_{ENVIRONMENT}',
    default_args=default_args,
    description=f'뉴스 수집 및 처리 파이프라인 (Kubernetes) [{ENVIRONMENT}]',
    schedule='0 */6 * * *',
    catchup=False,
    tags=['news', 'etl', 'pipeline', 'kubernetes', ENVIRONMENT],
    max_active_runs=1,
    max_active_tasks=3,
) as news_pipeline_dag:

    start = EmptyOperator(task_id='start_pipeline')

    collect_news = k8s_pod_operator(
        task_id='collect_news_k8s',
        image=get_airflow_variable(VAR_COLLECTOR_IMAGE),
        cmds=["python", "-m", "src.collectors.run_collector"],
        arguments=[
            "--kafka-servers", kafka_bootstrap_servers,
            "--run-once"
        ],
        env_vars={
            'KAFKA_BOOTSTRAP_SERVERS': kafka_bootstrap_servers,
            'MONGODB_URI': mongodb_uri,
            'DATABASE_NAME': database_name,
        },
        container_resources=worker_resources,
        startup_timeout_seconds=int(get_airflow_variable(VAR_COLLECTOR_TIMEOUT, "300")),
    )

    store_to_s3 = k8s_pod_operator(
        task_id='store_to_s3_k8s',
        image=get_airflow_variable(VAR_STORAGE_IMAGE),
        cmds=["python", "-m", "src.collectors.storage"],
        arguments=[
            "--run-once",
            "--wait-empty", get_airflow_variable(VAR_STORAGE_WAIT_EMPTY_SECONDS, "30"),
        ],
        env_vars={
            'KAFKA_BOOTSTRAP_SERVERS': kafka_bootstrap_servers,
            'AWS_REGION': aws_region,
            'S3_BUCKET_NAME': s3_bucket_name,
            'STORAGE_BATCH_SIZE': get_airflow_variable(VAR_STORAGE_BATCH_SIZE, "50"),
            'STORAGE_FLUSH_INTERVAL': get_airflow_variable(VAR_STORAGE_FLUSH_INTERVAL, "60"),
            'STORAGE_MAX_WORKERS': get_airflow_variable(VAR_STORAGE_MAX_WORKERS, "5"),
        },
        secrets=aws_secrets,
        container_resources=worker_resources,
        startup_timeout_seconds=int(get_airflow_variable(VAR_STORAGE_TIMEOUT, "300")),
    )

    process_text = k8s_pod_operator(
        task_id='process_text_k8s',
        image=get_airflow_variable(VAR_TEXT_PROCESSOR_IMAGE),
        cmds=["python", "-m", "src.processors.text.run_processor"],
        arguments=[
            "--mode", get_airflow_variable(VAR_TEXT_PROCESSOR_MODE, "stream"),
            "--run-once"
        ],
        env_vars={
            'KAFKA_BOOTSTRAP_SERVERS': kafka_bootstrap_servers,
            'MONGODB_URI': mongodb_uri,
            'DATABASE_NAME': database_name,
        },
        container_resources=worker_resources,
        startup_timeout_seconds=int(get_airflow_variable(VAR_TEXT_PROCESSOR_TIMEOUT, "300")),
    )

    process_sentiment = k8s_pod_operator(
        task_id='process_sentiment_k8s',
        image=get_airflow_variable(VAR_SENTIMENT_PROCESSOR_IMAGE),
        cmds=["python", "-m", "src.processors.sentiment.run_processor"],
        arguments=[
            "--mode", get_airflow_variable(VAR_SENTIMENT_PROCESSOR_MODE, "batch"),
            "--model-cache", sentiment_model_path
        ],
        env_vars={
            'KAFKA_BOOTSTRAP_SERVERS': kafka_bootstrap_servers,
            'MONGODB_URI': mongodb_uri,
            'DATABASE_NAME': database_name,
        },
        volumes=[model_volume],
        volume_mounts=[model_volume_mount_read_only],
        container_resources=worker_resources,
        startup_timeout_seconds=int(get_airflow_variable(VAR_SENTIMENT_PROCESSOR_TIMEOUT, "900")),
    )

    process_summary = k8s_pod_operator(
        task_id='process_summary_k8s',
        image=get_airflow_variable(VAR_SUMMARY_PROCESSOR_IMAGE),
        cmds=["python", "-m", "src.processors.summary.run_processor"],
        arguments=[
            "--mode", get_airflow_variable(VAR_SUMMARY_PROCESSOR_MODE, "batch"),
            "--model-path", summary_model_path
        ],
        env_vars={
            'KAFKA_BOOTSTRAP_SERVERS': kafka_bootstrap_servers,
            'MONGODB_URI': mongodb_uri,
            'DATABASE_NAME': database_name,
        },
        volumes=[model_volume],
        volume_mounts=[model_volume_mount_read_only],
        container_resources=worker_resources,
        startup_timeout_seconds=int(get_airflow_variable(VAR_SUMMARY_PROCESSOR_TIMEOUT, "900")),
        trigger_rule='all_done',
    )

    end = EmptyOperator(
        task_id='end_pipeline',
        trigger_rule='all_done',
    )

    start >> collect_news
    collect_news >> [store_to_s3, process_text]
    process_text >> process_sentiment
    [store_to_s3, process_sentiment] >> process_summary
    process_summary >> end
    store_to_s3 >> end

# ==========================================
# === Model Download DAG 정의 =============
# ==========================================
with DAG(
    dag_id=f'download_models_k8s_{ENVIRONMENT}',
    default_args=default_args,
    description=f'모델 다운로드 및 PVC 저장 (Kubernetes) [{ENVIRONMENT}]',
    schedule=None,
    catchup=False,
    tags=['model', 'setup', 'kubernetes', ENVIRONMENT],
) as download_model_dag:

    check_pvc = PythonOperator(
        task_id='check_pvc_exists',
        python_callable=check_pvc_exists,
        op_args=[model_pvc_name, k8s_namespace],
    )

    download_sentiment_script = f"""
        # 커스텀 이미지를 사용하는 것이 권장됩니다. (pip install 생략 가능)
        pip install transformers[torch] requests huggingface_hub;
        mkdir -p {sentiment_model_path};
        python -c "from transformers import AutoModel, AutoTokenizer; \\
                  model_name='{sentiment_model_hf_id}'; \\
                  AutoTokenizer.from_pretrained(model_name).save_pretrained('{sentiment_model_path}'); \\
                  AutoModel.from_pretrained(model_name).save_pretrained('{sentiment_model_path}');";
        echo 'Sentiment model downloaded.'
    """

    download_sentiment_model = k8s_pod_operator(
        task_id='download_sentiment_model_k8s',
        image=get_airflow_variable(VAR_MODEL_DOWNLOADER_IMAGE, 'python:3.11-slim'),
        cmds=["bash", "-cx"],
        arguments=[download_sentiment_script],
        volumes=[model_volume],
        volume_mounts=[model_volume_mount_read_write],
        container_resources=downloader_resources_sentiment,
        startup_timeout_seconds=int(get_airflow_variable(VAR_DOWNLOAD_SENTIMENT_TIMEOUT, "1200")),
    )

    download_summary_script = f"""
        # 커스텀 이미지를 사용하는 것이 권장됩니다. (pip install 생략 가능)
        pip install transformers[torch] sentencepiece;
        mkdir -p {summary_model_path};
        python -c "from transformers import BartForConditionalGeneration, PreTrainedTokenizerFast; \\
                  model_name='{summary_model_hf_id}'; \\
                  PreTrainedTokenizerFast.from_pretrained(model_name).save_pretrained('{summary_model_path}'); \\
                  BartForConditionalGeneration.from_pretrained(model_name).save_pretrained('{summary_model_path}');";
        echo 'Summary model downloaded.'
    """

    download_summary_model = k8s_pod_operator(
        task_id='download_summary_model_k8s',
        image=get_airflow_variable(VAR_MODEL_DOWNLOADER_IMAGE, 'python:3.11-slim'),
        cmds=["bash", "-cx"],
        arguments=[download_summary_script],
        volumes=[model_volume],
        volume_mounts=[model_volume_mount_read_write],
        container_resources=downloader_resources_summary,
        startup_timeout_seconds=int(get_airflow_variable(VAR_DOWNLOAD_SUMMARY_TIMEOUT, "1800")),
    )

    models_ready = EmptyOperator(task_id='models_ready')

    check_pvc >> [download_sentiment_model, download_summary_model] >> models_ready
    
