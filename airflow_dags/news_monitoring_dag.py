from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.operators.dummy import DummyOperator
from airflow.models import Variable, DagRun
from airflow.utils.session import create_session
from airflow.utils.db import provide_session
import requests
import json
import logging

# 기본 인자 정의
default_args = {
    'owner': 'airflow',
    'depends_on_past': False,
    'start_date': datetime(2023, 1, 1),
    'email': [Variable.get('EMAIL_NOTIFICATION', default='admin@example.com')],
    'email_on_failure': True,
    'email_on_retry': False,
    'retries': 1,
    'retry_delay': timedelta(minutes=1),
}

# DAG 정의
dag = DAG(
    'news_monitoring',
    default_args=default_args,
    description='뉴스 파이프라인 모니터링 및 알림',
    schedule_interval='0 */2 * * *',  # 2시간마다 실행
    catchup=False,
    tags=['monitoring', 'alerts'],
)

# 시작 연산자
start = DummyOperator(
    task_id='start_monitoring',
    dag=dag,
)

# MongoDB 연결 및 상태 확인
@provide_session
def check_mongodb_status(session=None, **context):
    import pymongo
    from pymongo.errors import ConnectionFailure
    
    mongodb_uri = Variable.get('MONGODB_URI', default='mongodb://mongodb:27017')
    database_name = Variable.get('DATABASE_NAME', default='news_db')
    
    try:
        client = pymongo.MongoClient(mongodb_uri, serverSelectionTimeoutMS=5000)
        db = client[database_name]
        # 간단한 명령어 실행으로 연결 확인
        db.command('ping')
        
        # 컬렉션 상태 확인
        collections = db.list_collection_names()
        news_count = db.news.count_documents({})
        processed_count = db.processed_news.count_documents({})
        topics_count = db.topics.count_documents({})
        sentiment_count = db.sentiment.count_documents({})
        
        logging.info(f"MongoDB 상태: 정상")
        logging.info(f"컬렉션: {collections}")
        logging.info(f"뉴스 수: {news_count}, 처리된 뉴스 수: {processed_count}")
        logging.info(f"토픽 수: {topics_count}, 감정 분석 수: {sentiment_count}")
        
        return {
            'status': 'success',
            'collections': collections,
            'news_count': news_count,
            'processed_count': processed_count,
            'topics_count': topics_count,
            'sentiment_count': sentiment_count
        }
        
    except ConnectionFailure:
        logging.error("MongoDB 연결 실패")
        return {'status': 'error', 'message': 'MongoDB 연결 실패'}
    except Exception as e:
        logging.error(f"MongoDB 상태 확인 중 오류 발생: {str(e)}")
        return {'status': 'error', 'message': str(e)}

# Kafka 상태 확인
def check_kafka_status(**context):
    import socket
    from kafka import KafkaAdminClient
    from kafka.errors import KafkaError
    
    kafka_servers = Variable.get('KAFKA_BOOTSTRAP_SERVERS', default='kafka:29092')
    
    try:
        # Kafka 연결 확인
        admin_client = KafkaAdminClient(bootstrap_servers=kafka_servers, client_id='airflow-monitor')
        topics = admin_client.list_topics()
        
        logging.info(f"Kafka 상태: 정상")
        logging.info(f"토픽 목록: {topics}")
        
        return {
            'status': 'success',
            'topics': topics
        }
        
    except KafkaError as e:
        logging.error(f"Kafka 연결 실패: {str(e)}")
        return {'status': 'error', 'message': str(e)}
    except Exception as e:
        logging.error(f"Kafka 상태 확인 중 오류 발생: {str(e)}")
        return {'status': 'error', 'message': str(e)}

# 파이프라인 DAG 실행 상태 확인
@provide_session
def check_pipeline_status(session=None, **context):
    try:
        dag_id = 'news_pipeline'
        # 최근 DAG 실행 가져오기
        dag_runs = session.query(DagRun).filter(
            DagRun.dag_id == dag_id
        ).order_by(DagRun.execution_date.desc()).limit(5).all()
        
        if not dag_runs:
            logging.warning(f"최근 {dag_id} 실행 이력이 없습니다.")
            return {'status': 'warning', 'message': f"최근 {dag_id} 실행 이력이 없습니다."}
        
        latest_run = dag_runs[0]
        status = latest_run.state
        execution_date = latest_run.execution_date
        
        logging.info(f"최근 파이프라인 실행 상태: {status}, 실행 일시: {execution_date}")
        
        # 실패한 경우 또는 오래된 경우 경고
        now = datetime.now()
        if status == 'failed':
            logging.error(f"파이프라인 실행 실패! 실행 일시: {execution_date}")
            return {'status': 'error', 'message': f"파이프라인 실행 실패! 실행 일시: {execution_date}"}
        elif (now - execution_date.replace(tzinfo=None)).total_seconds() > 24 * 3600:  # 24시간 이상 경과
            logging.warning(f"최근 파이프라인 실행이 24시간 이상 경과됨: {execution_date}")
            return {'status': 'warning', 'message': f"최근 파이프라인 실행이 24시간 이상 경과됨: {execution_date}"}
        
        return {
            'status': 'success',
            'pipeline_status': status,
            'execution_date': execution_date.isoformat()
        }
        
    except Exception as e:
        logging.error(f"파이프라인 상태 확인 중 오류 발생: {str(e)}")
        return {'status': 'error', 'message': str(e)}

# 모니터링 데이터 수집 및 보고서 생성
def collect_monitoring_data(**context):
    ti = context['task_instance']
    
    # 이전 태스크에서 수집한 데이터 가져오기
    mongodb_status = ti.xcom_pull(task_ids='check_mongodb')
    kafka_status = ti.xcom_pull(task_ids='check_kafka')
    pipeline_status = ti.xcom_pull(task_ids='check_pipeline')
    
    # 종합 보고서 데이터 생성
    report = {
        'timestamp': datetime.now().isoformat(),
        'mongodb': mongodb_status,
        'kafka': kafka_status,
        'pipeline': pipeline_status,
        'overall_status': 'success'  # 기본값
    }
    
    # 전체 상태 평가
    if any(item.get('status') == 'error' for item in [mongodb_status, kafka_status, pipeline_status] if item):
        report['overall_status'] = 'error'
    elif any(item.get('status') == 'warning' for item in [mongodb_status, kafka_status, pipeline_status] if item):
        report['overall_status'] = 'warning'
    
    logging.info(f"모니터링 보고서: {json.dumps(report, indent=2)}")
    
    # 오류가 있으면 별도 처리
    if report['overall_status'] != 'success':
        logging.warning("시스템 경고 또는 오류가 발생했습니다. 관리자에게 알림을 보냅니다.")
        # 여기에 알림 로직 추가 (이메일, 슬랙 등)
    
    return report

# 태스크 정의
check_mongodb = PythonOperator(
    task_id='check_mongodb',
    python_callable=check_mongodb_status,
    dag=dag,
)

check_kafka = PythonOperator(
    task_id='check_kafka',
    python_callable=check_kafka_status,
    dag=dag,
)

check_pipeline = PythonOperator(
    task_id='check_pipeline',
    python_callable=check_pipeline_status,
    dag=dag,
)

generate_report = PythonOperator(
    task_id='generate_monitoring_report',
    python_callable=collect_monitoring_data,
    dag=dag,
)

end = DummyOperator(
    task_id='end_monitoring',
    dag=dag,
)

# 태스크 의존성 설정
start >> [check_mongodb, check_kafka, check_pipeline] >> generate_report >> end 