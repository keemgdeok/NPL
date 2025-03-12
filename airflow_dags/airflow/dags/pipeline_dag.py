from datetime import datetime, timedelta
from airflow import DAG
from airflow.providers.docker.operators.docker import DockerOperator
from airflow.operators.python import PythonOperator
from airflow.operators.dummy import DummyOperator
from airflow.operators.bash import BashOperator
from airflow.models import Variable
from docker.types import Mount

default_args = {
    'owner': 'airflow',
    'depends_on_past': False,
    'start_date': datetime(2025, 3, 1),
    'email': [Variable.get('EMAIL_NOTIFICATION') or 'keemgdeok@gmail.com'],
    'email_on_failure': True,
    'email_on_retry': False,
    'retries': 1,
    'retry_delay': timedelta(minutes=5),
}

# 환경 변수 설정
KAFKA_BOOTSTRAP_SERVERS = Variable.get('KAFKA_BOOTSTRAP_SERVERS') or 'kafka:29092'
MONGODB_URI = Variable.get('MONGODB_URI') or 'mongodb://mongodb:27017'
DATABASE_NAME = Variable.get('DATABASE_NAME') or 'news_db'
DOCKER_NETWORK = Variable.get('DOCKER_NETWORK') or 'npl-network'
PROJECT_PATH = Variable.get('PROJECT_PATH') or '/opt/airflow/dags/project'

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

# DAG 정의
dag = DAG(
    'news_pipeline',
    default_args=default_args,
    description='뉴스 수집 및 처리 파이프라인',
    schedule_interval='0 */6 * * *',  # 6시간마다 실행
    catchup=False,
    tags=['news', 'etl', 'pipeline'],
)

# 시작 연산자
start = DummyOperator(
    task_id='start_pipeline',
    dag=dag,
)

# build_collector_image = BashOperator(
#     task_id='build_collector_image',
#     bash_command='cd /mnt/c/Users/keemg/npl && docker build -t collector:latest -f docker/collector.Dockerfile .',
#     dag=dag,
# )

# 뉴스 수집 작업
collect_news = DockerOperator(
    task_id='collect_news',
    image='npl-collector:latest',
    command='python -m src.collectors.run_collector --kafka-servers=kafka:29092 --run-once',
    environment={
        'KAFKA_BOOTSTRAP_SERVERS': KAFKA_BOOTSTRAP_SERVERS,
        'MONGODB_URI': MONGODB_URI,
        'DATABASE_NAME': DATABASE_NAME,
    },
    network_mode=DOCKER_NETWORK,
    docker_url='unix://var/run/docker.sock',
    api_version='auto',
    auto_remove='success',
    force_pull=False,
    dag=dag,
)

# S3 저장 작업
store_to_s3 = DockerOperator(
    task_id='store_to_s3',
    image='npl-storage:latest',
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
    network_mode=DOCKER_NETWORK,
    docker_url='unix://var/run/docker.sock',
    api_version='auto',
    auto_remove='success',
    force_pull=False,
    dag=dag,
)

# 텍스트 처리 작업
process_text = DockerOperator(
    task_id='process_text',
    image='npl-text-processor:latest',
    command='python -m src.processors.text.run_processor --mode stream --run-once',
    environment={
        'KAFKA_BOOTSTRAP_SERVERS': KAFKA_BOOTSTRAP_SERVERS,
        'MONGODB_URI': MONGODB_URI,
        'DATABASE_NAME': DATABASE_NAME,
    },
    network_mode=DOCKER_NETWORK,
    docker_url='unix://var/run/docker.sock',
    api_version='auto',
    auto_remove='success',
    force_pull=False,
    dag=dag,
)

# 토픽 처리 작업
# process_topics = DockerOperator(
#     task_id='process_topics',
#     image='topic-processor:latest',
#     command='--mode batch --days 7',
#     environment={
#         'KAFKA_BOOTSTRAP_SERVERS': KAFKA_BOOTSTRAP_SERVERS,
#         'MONGODB_URI': MONGODB_URI,
#         'DATABASE_NAME': DATABASE_NAME,
#     },
#     mounts=[models_mount],
#     network_mode=DOCKER_NETWORK,
#     docker_url='unix://var/run/docker.sock',
#     api_version='auto',
#     auto_remove='success',
#     dag=dag,
# )

# 감정 분석 작업
# process_sentiment = DockerOperator(
#     task_id='process_sentiment',
#     image='sentiment-processor:latest',
#     command='--mode batch --days 1',
#     environment={
#         'KAFKA_BOOTSTRAP_SERVERS': KAFKA_BOOTSTRAP_SERVERS,
#         'MONGODB_URI': MONGODB_URI,
#         'DATABASE_NAME': DATABASE_NAME,
#     },
#     network_mode=DOCKER_NETWORK,
#     docker_url='unix://var/run/docker.sock',
#     api_version='auto',
#     auto_remove='success',
#     dag=dag,
# )

# 토픽 모델 학습 작업 (주 1회 실행)
# train_topic_model = DockerOperator(
#     task_id='train_topic_model',
#     image='topic-processor:latest',
#     command='--mode train --days 30',
#     environment={
#         'KAFKA_BOOTSTRAP_SERVERS': KAFKA_BOOTSTRAP_SERVERS,
#         'MONGODB_URI': MONGODB_URI,
#         'DATABASE_NAME': DATABASE_NAME,
#     },
#     mounts=[models_mount],
#     network_mode=DOCKER_NETWORK,
#     docker_url='unix://var/run/docker.sock',
#     api_version='auto',
#     auto_remove='success',
#     trigger_rule='all_success',
#     dag=dag,
# )

# # 요약 보고서 생성 작업
# create_summary = DockerOperator(
#     task_id='create_summary',
#     image='topic-processor:latest',
#     command='--mode summarize',
#     environment={
#         'KAFKA_BOOTSTRAP_SERVERS': KAFKA_BOOTSTRAP_SERVERS,
#         'MONGODB_URI': MONGODB_URI,
#         'DATABASE_NAME': DATABASE_NAME,
#     },
#     mounts=[models_mount],
#     network_mode=DOCKER_NETWORK,
#     docker_url='unix://var/run/docker.sock',
#     api_version='auto',
#     auto_remove='success',
#     dag=dag,
# )

# 종료 연산자
end = DummyOperator(
    task_id='end_pipeline',
    dag=dag,
)

# 태스크 의존성 설정
start >> collect_news
collect_news >> [store_to_s3, process_text]
[store_to_s3, process_text] >> end

# [process_topics, process_sentiment]
# process_topics >> create_summary

# 매주 월요일에만 토픽 모델 재학습 실행
# from airflow.utils.trigger_rule import TriggerRule
# from airflow.operators.python import BranchPythonOperator

# def check_if_monday():
#     """현재 요일이 월요일인지 확인"""
#     if datetime.now().weekday() == 0:  # 0: 월요일
#         return 'train_topic_model'
#     else:
#         return 'end_pipeline'

# branch_task = BranchPythonOperator(
#     task_id='check_day_of_week',
#     python_callable=check_if_monday,
#     dag=dag,
# )

# process_topics >> branch_task >> [train_topic_model, end]
# process_sentiment >> end
# train_topic_model >> end
# create_summary >> end 