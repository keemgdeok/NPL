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
    'email': [Variable.get('EMAIL_NOTIFICATION', default='keemgdeok@gmail.com')],
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
MONGODB_URI = get_env_variable('MONGODB_URI', 'mongodb://mongodb:27017')
DATABASE_NAME = get_env_variable('DATABASE_NAME', 'news_db')
DOCKER_NETWORK = get_env_variable('DOCKER_NETWORK', 'npl-network')
PROJECT_PATH = get_env_variable('PROJECT_PATH', '/opt/airflow/dags/project')

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
    source=f'{PROJECT_PATH}/models',
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
    network_mode: str = DOCKER_NETWORK,
    auto_remove: bool = True,
    api_version: str = 'auto',
    force_pull: bool = False,
    trigger_rule: str = 'all_success',
    retries: int = 3,
    retry_delay: timedelta = timedelta(minutes=5),
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
        dag=dag,
    )

# DAG 정의
with DAG(
    'news_pipeline',
    default_args=default_args,
    description='뉴스 수집 및 처리 파이프라인',
    schedule_interval='0 */6 * * *',  # 6시간마다 실행
    catchup=False,
    tags=['news', 'etl', 'pipeline'],
    max_active_runs=1,
    concurrency=3,
) as dag:
    
    # 시작 연산자
    start = DummyOperator(
        task_id='start_pipeline',
    )
    
    # 뉴스 수집 작업
    collect_news = create_docker_operator(
        task_id='collect_news',
        image='npl-collector:v1.0.0',
        command='python -m src.collectors.run_collector --kafka-servers=kafka:29092 --run-once',
        environment={
            'KAFKA_BOOTSTRAP_SERVERS': KAFKA_BOOTSTRAP_SERVERS,
            'MONGODB_URI': MONGODB_URI,
            'DATABASE_NAME': DATABASE_NAME,
        },
        dag=dag,
    )
    
    # S3 저장 작업
    store_to_s3 = create_docker_operator(
        task_id='store_to_s3',
        image='npl-storage:v1.0.0',
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
        image='npl-text-processor:v1.0.0',
        command='python -m src.processors.text.run_processor --mode stream --run-once',
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
        image='npl-sentiment:v1.0.0',
        command='python -m src.processors.sentiment.run_processor --mode batch --model-cache=/app/models/kr-finbert-sc',
        environment={
            'KAFKA_BOOTSTRAP_SERVERS': KAFKA_BOOTSTRAP_SERVERS,
            'MONGODB_URI': MONGODB_URI,
            'DATABASE_NAME': DATABASE_NAME,
        },
        mounts=[models_mount],
        dag=dag,
    )
    
    # 요약 처리 작업
    process_summary = create_docker_operator(
        task_id='process_summary',
        image='npl-summary-processor:v1.0.0',
        command='python -m src.processors.summary.run_processor --mode batch --model-path=/app/models/kobart-summarization-model',
        environment={
            'KAFKA_BOOTSTRAP_SERVERS': KAFKA_BOOTSTRAP_SERVERS,
            'MONGODB_URI': MONGODB_URI,
            'DATABASE_NAME': DATABASE_NAME,
        },
        mounts=[models_mount],
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
    process_text >> process_sentiment
    [store_to_s3, process_sentiment] >> process_summary
    [process_sentiment, process_summary, store_to_s3] >> end

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
        bash_command=f'mkdir -p {PROJECT_PATH}/models/kr-finbert-sc && '
                    f'python -m src.processors.sentiment.setup --output-dir={PROJECT_PATH}/models/kr-finbert-sc',
    )
    
    download_summary_model = BashOperator(
        task_id='download_summary_model',
        bash_command=f'mkdir -p {PROJECT_PATH}/models/kobart-summarization-model && '
                    f'python -m src.processors.summary.setup --output-dir={PROJECT_PATH}/models/kobart-summarization-model',
    )
    
    models_ready = DummyOperator(
        task_id='models_ready',
    )
    
    [download_sentiment_model, download_summary_model] >> models_ready 
    
