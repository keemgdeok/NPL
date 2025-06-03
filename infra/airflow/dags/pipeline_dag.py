from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from airflow import DAG
from airflow.providers.docker.operators.docker import DockerOperator
from airflow.operators.python import PythonOperator
from airflow.operators.dummy import DummyOperator
from airflow.operators.bash import BashOperator
from airflow.models import Variable
from docker.types import Mount

# 기본 인자 정의
default_args = {
    'owner': 'airflow',
    'depends_on_past': False,
    'start_date': datetime(2025, 3, 1),
    'email': [Variable.get('EMAIL_NOTIFICATION', 'keemgdeok@gmail.com')],
    'email_on_failure': True,
    'email_on_retry': False,
    'retries': 3,
    'retry_delay': timedelta(minutes=5),
    'execution_timeout': timedelta(hours=2),
}

# 환경 변수 설정 (기본값 제공 및 타입 캐스팅 적용)
def get_env_variable(name: str, default: Optional[str] = None) -> str:
    """환경 변수를 가져오고 없는 경우 기본값 반환"""
    try:
        return Variable.get(name)
    except KeyError:
        if default is not None:
            return default
        raise ValueError(f"필수 환경 변수 {name}이(가) 설정되지 않았습니다.")

# 주요 환경 변수 설정
KAFKA_BOOTSTRAP_SERVERS = get_env_variable('KAFKA_BOOTSTRAP_SERVERS', 'kafka:29092')
MONGODB_URI = get_env_variable('MONGODB_URI', 'mongodb://npl-mongodb:27017')
DATABASE_NAME = get_env_variable('DATABASE_NAME', 'news_db')
DOCKER_NETWORK = get_env_variable('DOCKER_NETWORK', 'news-pipeline')
# docker-compose-airflow.yml에서 마운트된 실제 경로 사용
MODELS_PATH = get_env_variable('MODELS_PATH', '/opt/airflow/models_storage')

# S3 환경 변수
try:
    AWS_ACCESS_KEY_ID = Variable.get('AWS_ACCESS_KEY_ID')
    AWS_SECRET_ACCESS_KEY = Variable.get('AWS_SECRET_ACCESS_KEY')
    AWS_REGION = Variable.get('AWS_REGION')
    S3_BUCKET_NAME = Variable.get('S3_BUCKET_NAME')
except KeyError:
    AWS_ACCESS_KEY_ID = None
    AWS_SECRET_ACCESS_KEY = None
    AWS_REGION = 'ap-northeast-2'
    S3_BUCKET_NAME = 'aws-s3-keemgdeok'

# 마운트 설정
models_mount = Mount(
    source=MODELS_PATH,  # docker-compose에서 마운트된 실제 경로 사용
    target='/app/models',
    type='bind'
)

# 공통 Docker 연산자 설정
def create_docker_operator(
    task_id: str,
    image: str,
    command: str,
    environment: Dict[str, str],
    mounts: Optional[List[Mount]] = None,
    docker_url: str = 'unix://var/run/docker.sock',
    network_mode: str = 'news-pipeline',  # 명시적으로 news-pipeline 네트워크 사용
    auto_remove: str = 'success',
    api_version: str = 'auto',
    force_pull: bool = False,
    trigger_rule: str = 'all_success',
    retries: int = 3,
    retry_delay: timedelta = timedelta(minutes=5),
    mount_tmp_dir: bool = False,
    extra_hosts: Optional[Dict[str, str]] = None,
    dag: Optional[DAG] = None
) -> DockerOperator:
    """Docker 연산자를 일관된 설정으로 생성하는 헬퍼 함수"""
    return DockerOperator(
        task_id=task_id,
        image=image,
        command=command,
        environment=environment,
        mounts=mounts or [],
        docker_url=docker_url,
        network_mode=network_mode,
        auto_remove=auto_remove,
        api_version=api_version,
        force_pull=force_pull,
        trigger_rule=trigger_rule,
        retries=retries,
        retry_delay=retry_delay,
        mount_tmp_dir=mount_tmp_dir,
        extra_hosts=extra_hosts or {},
        dag=dag,
    )

# DAG 정의
with DAG(
    'news_pipeline',
    default_args=default_args,
    description='뉴스 수집 및 처리 파이프라인',
    schedule_interval='*/30 * * * *',  # 30분마다 실행
    catchup=False,
    tags=['news', 'etl', 'pipeline'],
    max_active_runs=1,
    concurrency=3,
) as dag:
    
    # 시작 연산자
    start = DummyOperator(
        task_id='start_pipeline',
    )
    
    # 뉴스 수집 작업 (원래 DockerOperator 정의로 복원)
    # KAFKA_SERVICE_IP, KAFKA_SERVICE_PORT, KAFKA_IP_ADDRESS_FOR_COLLECTOR, bash_collect_command/collect_news_command_list 변수 삭제

    collect_news = create_docker_operator(
        task_id='collect_news',
        image='news-pipeline-collector:latest',
        command='python -m src.collectors.run_collector --kafka-servers=kafka:29092 --run-once',
        environment={
            'KAFKA_BOOTSTRAP_SERVERS': KAFKA_BOOTSTRAP_SERVERS, # KAFKA_BOOTSTRAP_SERVERS는 'kafka:29092'를 기본값으로 가짐
            'MONGODB_URI': MONGODB_URI,
            'DATABASE_NAME': DATABASE_NAME,
            'KAFKA_CONNECTION_RETRY': '5',
            'KAFKA_CONNECTION_RETRY_DELAY': '5',
            'KAFKA_REQUEST_TIMEOUT_MS': '60000',
            'KAFKA_API_VERSION_AUTO_TIMEOUT_MS': '60000',
            'KAFKA_MAX_BLOCK_MS': '60000',
            'KAFKA_API_VERSION': '0.10.2',
        },
        # extra_hosts 제거 - 같은 네트워크 내에서는 호스트명으로 통신 가능
        dag=dag,
    )
    
    # S3 저장 작업
    store_to_s3 = create_docker_operator(
        task_id='store_to_s3',
        image='news-pipeline-storage:latest',
        command='python -m src.collectors.storage --run-once --wait-empty 30',
        environment={
            'KAFKA_BOOTSTRAP_SERVERS': KAFKA_BOOTSTRAP_SERVERS,
            'AWS_ACCESS_KEY_ID': AWS_ACCESS_KEY_ID,
            'AWS_SECRET_ACCESS_KEY': AWS_SECRET_ACCESS_KEY,
            'AWS_REGION': AWS_REGION,
            'S3_BUCKET_NAME': S3_BUCKET_NAME,
            'STORAGE_BATCH_SIZE': '50',
            'STORAGE_FLUSH_INTERVAL': '60',
            'STORAGE_MAX_WORKERS': '5',
        },
        dag=dag,
    )
    
    # 텍스트 처리 작업
    process_text = create_docker_operator(
        task_id='process_text',
        image='news-pipeline-text-processor:latest',
        command='python -m src.processors.text.run_processor --run-once',
        environment={
            'KAFKA_BOOTSTRAP_SERVERS': KAFKA_BOOTSTRAP_SERVERS,
            'MONGODB_URI': MONGODB_URI,
            'DATABASE_NAME': DATABASE_NAME,
        },
        dag=dag,
    )
    
    # 감정 분석 작업
    process_sentiment = create_docker_operator(
        task_id='process_sentiment',
        image='news-pipeline-sentiment-processor:latest',
        command='python -m src.processors.sentiment.run_processor',  # 모든 옵션 제거
        environment={
            'KAFKA_BOOTSTRAP_SERVERS': KAFKA_BOOTSTRAP_SERVERS,
            'MONGODB_URI': MONGODB_URI,
            'DATABASE_NAME': DATABASE_NAME,
        },
        dag=dag,
    )
    
    # 요약 처리 작업
    process_summary = create_docker_operator(
        task_id='process_summary',
        image='news-pipeline-summary-processor:latest',
        command='python -m src.processors.summary.run_processor',  # 모든 옵션 제거
        environment={
            'KAFKA_BOOTSTRAP_SERVERS': KAFKA_BOOTSTRAP_SERVERS,
            'MONGODB_URI': MONGODB_URI,
            'DATABASE_NAME': DATABASE_NAME,
        },
        dag=dag,
        trigger_rule='all_done',  # 이전 작업들 중 일부가 실패해도 실행
    )
    
    # 종료 연산자
    end = DummyOperator(
        task_id='end_pipeline',
        trigger_rule='all_done',  # 모든 이전 작업이 완료되면 실행 (성공/실패 상관없이)
    )
    
    # 태스크 의존성 설정
    start >> collect_news
    collect_news >> [store_to_s3, process_text]
    process_text >> [process_sentiment, process_summary]
    [process_sentiment, process_summary] >> end

# 감정 분석 모델 다운로드를 위한 별도 DAG
with DAG(
    'download_sentiment_model',
    default_args=default_args,
    description='감정 분석 모델 다운로드',
    schedule_interval=None,  # 수동 실행만 가능
    catchup=False,
    tags=['model', 'setup'],
) as download_model_dag:
    
    download_sentiment_model = BashOperator(
        task_id='download_sentiment_model',
        bash_command=f'mkdir -p /opt/airflow/models_storage/kr-finbert-sc && '
                    f'python -m src.processors.sentiment.setup --output-dir=/opt/airflow/models_storage/kr-finbert-sc',
    )
    
    models_ready = DummyOperator(
        task_id='models_ready',
    )
    
    [download_sentiment_model] >> models_ready 
    
