from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple, Union
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.operators.dummy import DummyOperator
from airflow.models import Variable, DagRun
from airflow.utils.session import create_session
from airflow.utils.db import provide_session
from airflow.hooks.base import BaseHook
from airflow.exceptions import AirflowException
import requests
import json
import logging
import os
import sys

# 라이브러리 의존성 확인
REQUIRED_PACKAGES = [
    "pymongo",
    "kafka-python",
    "requests"
]

# 패키지 설치 여부 확인
def check_and_install_packages():
    """필요한 패키지가 설치되어 있는지 확인하고 없으면 설치합니다."""
    import importlib.util
    import subprocess
    
    missing_packages = []
    for package in REQUIRED_PACKAGES:
        package_name = package.split("==")[0] if "==" in package else package
        spec = importlib.util.find_spec(package_name.replace("-", "_"))
        if spec is None:
            missing_packages.append(package)
    
    if missing_packages:
        logging.warning(f"누락된 패키지를 설치합니다: {', '.join(missing_packages)}")
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", "--user"] + missing_packages)
            logging.info("모든 패키지가 성공적으로 설치되었습니다.")
        except subprocess.CalledProcessError as e:
            logging.error(f"패키지 설치 중 오류 발생: {str(e)}")
            raise AirflowException(f"필수 패키지 설치 실패: {str(e)}")

# 필요한 패키지가 설치되어 있는지 확인
check_and_install_packages()

# 기본 인자 정의
default_args = {
    'owner': 'airflow',
    'depends_on_past': False,
    'start_date': datetime(2025, 3, 1),
    'email': [Variable.get('EMAIL_NOTIFICATION', default='keemgdeok@gmail.com')],
    'email_on_failure': True,
    'email_on_retry': False,
    'retries': 2,
    'retry_delay': timedelta(minutes=1),
}

# 알림 관련 설정
def get_notification_settings() -> Dict[str, Any]:
    """알림 설정을 가져옵니다."""
    settings = {
        'enabled': Variable.get('ENABLE_NOTIFICATIONS', default='true').lower() == 'true',
        'slack_webhook': Variable.get('SLACK_WEBHOOK_URL', default=''),
        'ms_teams_webhook': Variable.get('MS_TEAMS_WEBHOOK_URL', default=''),
        'email_recipients': Variable.get('ALERT_EMAIL_RECIPIENTS', default='').split(','),
    }
    return settings

# 알림 전송 함수
def send_notification(level: str, message: str, details: Optional[Dict[str, Any]] = None) -> bool:
    """알림을 지정된 채널로 전송합니다.
    
    Args:
        level: 알림 레벨 (info, warning, error)
        message: 알림 메시지
        details: 추가 세부 정보 (dict)
        
    Returns:
        성공 여부
    """
    settings = get_notification_settings()
    
    if not settings['enabled']:
        logging.info(f"알림이 비활성화되어 있습니다. 메시지: {message}")
        return True
    
    success = True
    
    # 이메일 알림
    if level in ['warning', 'error'] and settings['email_recipients']:
        try:
            from airflow.utils.email import send_email
            
            subject = f"[뉴스 파이프라인 알림] {level.upper()}: {message[:50]}..."
            body = f"""
            <h2>{level.upper()}: {message}</h2>
            <p>시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
            {"<pre>" + json.dumps(details, indent=2) + "</pre>" if details else ""}
            """
            
            send_email(
                to=settings['email_recipients'],
                subject=subject,
                html_content=body
            )
            logging.info(f"이메일 알림 전송 성공: {subject}")
        except Exception as e:
            logging.error(f"이메일 알림 전송 실패: {str(e)}")
            success = False
    
    # Slack 알림
    if settings['slack_webhook']:
        try:
            color = {'info': '#36a64f', 'warning': '#ffcc00', 'error': '#ff0000'}
            
            payload = {
                "attachments": [
                    {
                        "color": color.get(level, '#36a64f'),
                        "title": f"{level.upper()}: {message}",
                        "text": json.dumps(details, indent=2) if details else "",
                        "footer": f"뉴스 파이프라인 모니터링 | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                    }
                ]
            }
            
            response = requests.post(
                settings['slack_webhook'],
                data=json.dumps(payload),
                headers={'Content-Type': 'application/json'}
            )
            
            if response.status_code != 200:
                logging.error(f"Slack 알림 전송 실패: {response.text}")
                success = False
            else:
                logging.info(f"Slack 알림 전송 성공: {level.upper()} - {message}")
        except Exception as e:
            logging.error(f"Slack 알림 전송 중 오류 발생: {str(e)}")
            success = False
    
    return success

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

# MongoDB 컬렉션 설정
def get_mongodb_collections() -> Dict[str, str]:
    """MongoDB 컬렉션 설정을 가져옵니다."""
    return {
        'news': Variable.get('MONGODB_NEWS_COLLECTION', default='news_articles'),
        'processed': Variable.get('MONGODB_PROCESSED_COLLECTION', default='processed_articles'),
        'topics': Variable.get('MONGODB_TOPICS_COLLECTION', default='topic_articles'),
        'sentiment': Variable.get('MONGODB_SENTIMENT_COLLECTION', default='sentiment_articles'),
        'summary': Variable.get('MONGODB_SUMMARY_COLLECTION', default='summary_articles'),
    }

# MongoDB 연결 및 상태 확인
@provide_session
def check_mongodb_status(session=None, **context) -> Dict[str, Any]:
    """MongoDB 연결 상태와 컬렉션 정보를 확인합니다."""
    import pymongo
    from pymongo.errors import ConnectionFailure
    
    mongodb_uri = Variable.get('MONGODB_URI', default='mongodb://mongodb:27017')
    database_name = Variable.get('DATABASE_NAME', default='news_db')
    collections_config = get_mongodb_collections()
    
    try:
        client = pymongo.MongoClient(mongodb_uri, serverSelectionTimeoutMS=5000)
        db = client[database_name]
        # 간단한 명령어 실행으로 연결 확인
        db.command('ping')
        
        # 컬렉션 상태 확인
        all_collections = db.list_collection_names()
        logging.info(f"사용 가능한 컬렉션 목록: {all_collections}")
        
        # 각 컬렉션 문서 수 확인
        collection_counts = {}
        missing_collections = []
        
        for key, collection_name in collections_config.items():
            if collection_name in all_collections:
                count = db[collection_name].count_documents({})
                collection_counts[collection_name] = count
            else:
                missing_collections.append(collection_name)
        
        result = {
            'status': 'success',
            'collections': all_collections,
            'collection_counts': collection_counts
        }
        
        # 누락된 컬렉션이 있는 경우 경고
        if missing_collections:
            result['status'] = 'warning'
            result['missing_collections'] = missing_collections
            logging.warning(f"누락된 컬렉션: {missing_collections}")
            send_notification('warning', 
                             f"MongoDB에 {len(missing_collections)}개의 컬렉션이 누락되었습니다",
                             {'missing_collections': missing_collections})
        
        logging.info(f"MongoDB 상태: {result['status']}")
        logging.info(f"컬렉션 문서 수: {collection_counts}")
        
        return result
        
    except ConnectionFailure:
        error_msg = "MongoDB 연결 실패"
        logging.error(error_msg)
        send_notification('error', error_msg, {'uri': mongodb_uri})
        return {'status': 'error', 'message': error_msg}
    except Exception as e:
        error_msg = f"MongoDB 상태 확인 중 오류 발생: {str(e)}"
        logging.error(error_msg)
        send_notification('error', error_msg)
        return {'status': 'error', 'message': str(e)}

# Kafka 상태 확인
def check_kafka_status(**context) -> Dict[str, Any]:
    """Kafka 연결 상태와 토픽 정보를 확인합니다."""
    import socket
    from kafka import KafkaAdminClient
    from kafka.errors import KafkaError
    
    kafka_servers = Variable.get('KAFKA_BOOTSTRAP_SERVERS', default='kafka:29092')
    expected_topics = Variable.get('KAFKA_EXPECTED_TOPICS', default='').split(',')
    expected_topics = [t.strip() for t in expected_topics if t.strip()]
    
    try:
        # Kafka 연결 확인
        admin_client = KafkaAdminClient(bootstrap_servers=kafka_servers, client_id='airflow-monitor')
        topics = admin_client.list_topics()
        
        result = {
            'status': 'success',
            'topics': topics
        }
        
        # 예상 토픽 확인
        if expected_topics:
            missing_topics = [t for t in expected_topics if t not in topics]
            if missing_topics:
                result['status'] = 'warning'
                result['missing_topics'] = missing_topics
                logging.warning(f"누락된 Kafka 토픽: {missing_topics}")
                send_notification('warning', 
                                 f"Kafka에 {len(missing_topics)}개의 토픽이 누락되었습니다",
                                 {'missing_topics': missing_topics})
        
        logging.info(f"Kafka 상태: {result['status']}")
        logging.info(f"토픽 목록: {topics}")
        
        return result
        
    except KafkaError as e:
        error_msg = f"Kafka 연결 실패: {str(e)}"
        logging.error(error_msg)
        send_notification('error', error_msg, {'servers': kafka_servers})
        return {'status': 'error', 'message': str(e)}
    except Exception as e:
        error_msg = f"Kafka 상태 확인 중 오류 발생: {str(e)}"
        logging.error(error_msg)
        send_notification('error', error_msg)
        return {'status': 'error', 'message': str(e)}

# 파이프라인 DAG 실행 상태 확인
@provide_session
def check_pipeline_status(session=None, **context) -> Dict[str, Any]:
    """뉴스 파이프라인 DAG의 실행 상태를 확인합니다."""
    try:
        dag_id = 'news_pipeline'
        # 최근 DAG 실행 가져오기
        dag_runs = session.query(DagRun).filter(
            DagRun.dag_id == dag_id
        ).order_by(DagRun.execution_date.desc()).limit(5).all()
        
        if not dag_runs:
            warning_msg = f"최근 {dag_id} 실행 이력이 없습니다."
            logging.warning(warning_msg)
            send_notification('warning', warning_msg)
            return {'status': 'warning', 'message': warning_msg}
        
        latest_run = dag_runs[0]
        status = latest_run.state
        execution_date = latest_run.execution_date
        
        logging.info(f"최근 파이프라인 실행 상태: {status}, 실행 일시: {execution_date}")
        
        # 실패한 경우 또는 오래된 경우 경고
        now = datetime.now()
        if status == 'failed':
            error_msg = f"파이프라인 실행 실패! 실행 일시: {execution_date}"
            logging.error(error_msg)
            send_notification('error', error_msg, {
                'dag_id': dag_id,
                'run_id': latest_run.run_id,
                'execution_date': execution_date.isoformat()
            })
            return {'status': 'error', 'message': error_msg}
        elif (now - execution_date.replace(tzinfo=None)).total_seconds() > 24 * 3600:  # 24시간 이상 경과
            warning_msg = f"최근 파이프라인 실행이 24시간 이상 경과됨: {execution_date}"
            logging.warning(warning_msg)
            send_notification('warning', warning_msg)
            return {'status': 'warning', 'message': warning_msg}
        
        return {
            'status': 'success',
            'pipeline_status': status,
            'execution_date': execution_date.isoformat()
        }
        
    except Exception as e:
        error_msg = f"파이프라인 상태 확인 중 오류 발생: {str(e)}"
        logging.error(error_msg)
        send_notification('error', error_msg)
        return {'status': 'error', 'message': str(e)}

# 모니터링 데이터 수집 및 보고서 생성
def collect_monitoring_data(**context) -> Dict[str, Any]:
    """모니터링 정보를 수집하고 종합 보고서를 생성합니다."""
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
    
    # 오류 또는 경고가 있으면 알림 전송
    if report['overall_status'] == 'error':
        send_notification('error', "시스템에 오류가 발생했습니다", report)
    elif report['overall_status'] == 'warning':
        send_notification('warning', "시스템에 경고가 발생했습니다", report)
    else:
        # 성공 보고서도 정보성 알림으로 전송 가능
        if Variable.get('SEND_SUCCESS_NOTIFICATIONS', default='false').lower() == 'true':
            send_notification('info', "모니터링 정상 완료", report)
    
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