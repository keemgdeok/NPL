from __future__ import annotations

import pendulum

from datetime import timedelta
from typing import Dict, Any

from airflow.models.dag import DAG
from airflow.providers.cncf.kubernetes.operators.pod import KubernetesPodOperator
from airflow.operators.empty import EmptyOperator
from airflow.models import Variable

# Kubernetes 관련 모듈 임포트
from kubernetes.client import models as k8s

# --- 기본 설정 및 K8s 리소스 참조 ---
K8S_NAMESPACE = Variable.get("K8S_NAMESPACE", default_var="airflow")

# 사용할 모니터링 도구 이미지
MONITORING_IMAGE_DEFAULT = "your-registry.com/monitoring-tools:latest" # 기본값 상수로 분리
MONITORING_IMAGE = Variable.get("MONITORING_IMAGE", default_var=MONITORING_IMAGE_DEFAULT)

# 스크립트 경로 (이미지 내 경로)
MONITORING_SCRIPT_PATH = "/opt/scripts/monitoring_script.py" # 예시 경로

# K8s Secret 이름 정의 (실제 생성된 Secret 이름 사용)
MONGODB_SECRET_NAME = Variable.get("MONGODB_K8S_SECRET_NAME", default_var="mongodb-credentials")
SLACK_SECRET_NAME = Variable.get("SLACK_K8S_SECRET_NAME", default_var="slack-webhook")
TEAMS_SECRET_NAME = Variable.get("TEAMS_K8S_SECRET_NAME", default_var="teams-webhook")
# 이메일 알림은 Airflow 자체 기능 사용 또는 전용 Pod/스크립트 필요 (여기서는 제외)

# Worker Pod 기본 리소스 설정 (V1ResourceRequirements 객체 사용)
MONITORING_RESOURCES = k8s.V1ResourceRequirements(
    requests={"cpu": "200m", "memory": "256Mi"},
    limits={"cpu": "500m", "memory": "512Mi"}
)

# --- DAG 기본 인자 ---
default_args = {
    'owner': 'airflow',
    'depends_on_past': False,
    'start_date': pendulum.datetime(2025, 3, 1, tz="Asia/Seoul"),
    'email': [Variable.get('EMAIL_NOTIFICATION', default_var='keemgdeok@gmail.com')], # default_var 사용 확인
    'email_on_failure': True, # DAG 실패 시 Airflow 기본 알림
    'email_on_retry': False,
    'retries': 1, # Pod 생성 실패 등에 대한 재시도
    'retry_delay': timedelta(minutes=2),
}

# --- DAG 정의 ---
with DAG(
    dag_id='news_monitoring_k8s',
    default_args=default_args,
    description='뉴스 파이프라인 모니터링 및 알림 (Kubernetes)',
    schedule='0 */2 * * *',
    catchup=False,
    tags=['monitoring', 'alerts', 'kubernetes'],
) as dag:

    start = EmptyOperator(task_id='start_monitoring')

    # --- 모니터링 태스크 (KubernetesPodOperator) ---

    # MongoDB 상태 확인 Pod
    check_mongodb = KubernetesPodOperator(
        task_id='check_mongodb_k8s',
        namespace=K8S_NAMESPACE,
        image=MONITORING_IMAGE,
        name='check-mongodb-pod',
        cmds=["python", MONITORING_SCRIPT_PATH],
        arguments=["--check", "mongo"],
        env_from=[ # Secret의 모든 키를 환경 변수로 가져오기 (스크립트에서 파싱 가정)
            k8s.V1EnvFromSource(secret_ref=k8s.V1SecretEnvSource(name=MONGODB_SECRET_NAME)),
            k8s.V1EnvFromSource(secret_ref=k8s.V1SecretEnvSource(name=SLACK_SECRET_NAME, optional=True)), # 없으면 무시
            k8s.V1EnvFromSource(secret_ref=k8s.V1SecretEnvSource(name=TEAMS_SECRET_NAME, optional=True)),
        ],
        env_vars={ # 추가 환경 변수
            "DATABASE_NAME": Variable.get('DATABASE_NAME', default_var='news_db'),
            # 필요시 컬렉션 이름 등 추가
        },
        get_logs=True,
        on_finish_action="delete_pod",
        container_resources=MONITORING_RESOURCES,
        startup_timeout_seconds=180,
    )

    # Kafka 상태 확인 Pod
    check_kafka = KubernetesPodOperator(
        task_id='check_kafka_k8s',
        namespace=K8S_NAMESPACE,
        image=MONITORING_IMAGE,
        name='check-kafka-pod',
        cmds=["python", MONITORING_SCRIPT_PATH],
        arguments=["--check", "kafka"],
        env_from=[ # 웹훅 Secret 참조
            k8s.V1EnvFromSource(secret_ref=k8s.V1SecretEnvSource(name=SLACK_SECRET_NAME, optional=True)),
            k8s.V1EnvFromSource(secret_ref=k8s.V1SecretEnvSource(name=TEAMS_SECRET_NAME, optional=True)),
        ],
        env_vars={
            "KAFKA_BOOTSTRAP_SERVERS": Variable.get('KAFKA_BOOTSTRAP_SERVERS', default_var='kafka.airflow.svc.cluster.local:9092'),
            # 필요시 예상 토픽 목록 등 추가
        },
        get_logs=True,
        on_finish_action="delete_pod",
        container_resources=MONITORING_RESOURCES,
        startup_timeout_seconds=180,
    )

    # 파이프라인 DAG 상태 확인 Pod
    # 이 Pod는 Airflow DB에 접근해야 할 수 있으므로, Airflow Webserver/Scheduler와 동일한 이미지 또는
    # Airflow 라이브러리가 설치된 이미지를 사용하고, DB 접속 정보를 Secret/ConfigMap으로 받아야 함
    check_pipeline = KubernetesPodOperator(
        task_id='check_pipeline_status_k8s',
        namespace=K8S_NAMESPACE,
        image=Variable.get("AIRFLOW_WORKER_IMAGE", default_var=MONITORING_IMAGE_DEFAULT),
        name='check-pipeline-pod',
        cmds=["python", MONITORING_SCRIPT_PATH],
        arguments=["--check", "pipeline",
                   "--target-dag-id", "news_pipeline_k8s", # 확인할 DAG ID 전달
                   "--max-duration-hours", "8"], # 예: 최대 실행 시간 임계값
        env_from=[ # DB 접속 정보 및 웹훅 Secret 참조
            # 가정: airflow-configmap에 DB 연결 정보가 환경 변수로 정의되어 있음
            k8s.V1EnvFromSource(config_map_ref=k8s.V1ConfigMapEnvSource(name="airflow-configmap")),
            # 가정: airflow-secrets에 DB 비밀번호가 정의되어 있음 (또는 postgres-secret 사용)
            k8s.V1EnvFromSource(secret_ref=k8s.V1SecretEnvSource(name="airflow-secrets")),
            k8s.V1EnvFromSource(secret_ref=k8s.V1SecretEnvSource(name=SLACK_SECRET_NAME, optional=True)),
            k8s.V1EnvFromSource(secret_ref=k8s.V1SecretEnvSource(name=TEAMS_SECRET_NAME, optional=True)),
        ],
        # Pod가 Airflow DB에 접근할 수 있는 ServiceAccount 사용 필요시 설정
        # service_account_name="airflow-worker-serviceaccount",
        get_logs=True,
        on_finish_action="delete_pod",
        container_resources=MONITORING_RESOURCES,
        startup_timeout_seconds=180,
    )

    end = EmptyOperator(
        task_id='end_monitoring',
        # 모든 모니터링 작업이 성공적으로 완료되어야 DAG 성공 처리
        # 개별 작업 실패 시 해당 Pod에서 알림을 보내고 태스크는 실패 처리됨
        # Airflow의 기본 email_on_failure가 DAG 레벨 실패 알림을 보낼 수 있음
        trigger_rule='all_success',
    )

    # --- 태스크 의존성 설정 ---
    start >> [check_mongodb, check_kafka, check_pipeline] >> end 