import argparse
import os
import sys
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, Optional

import requests

# --- 로깅 설정 ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("airflow_monitoring_script")

# --- 환경 변수에서 설정 로드 ---
# 알림 관련 (Secret에서 주입됨, optional=True 처리된 Secret은 없을 수 있음)
SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL")
TEAMS_WEBHOOK_URL = os.getenv("MS_TEAMS_WEBHOOK_URL") # DAG에서 사용된 이름과 일치 필요

# MongoDB 관련 (Secret 및 env_vars에서 주입됨)
MONGODB_URI = os.getenv("MONGODB_URI") # Secret에서 주입 권장 (비밀번호 포함 시)
DATABASE_NAME = os.getenv("DATABASE_NAME", "news_db")
# 필요시 컬렉션 이름도 환경 변수로 받기
MONGODB_NEWS_COLLECTION = os.getenv("MONGODB_NEWS_COLLECTION", "news_articles")
MONGODB_PROCESSED_COLLECTION = os.getenv("MONGODB_PROCESSED_COLLECTION", "processed_articles")

# Kafka 관련 (env_vars에서 주입됨)
KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS")

# 파이프라인 확인 관련 (arguments 및 env_vars에서 주입됨)
# TARGET_DAG_ID, MAX_DURATION_HOURS 등은 argparse로 받음
AIRFLOW_CONN_ID = "airflow_db" # Airflow 메타데이터 DB Connection ID (기본값)

# --- 알림 함수 ---
def send_notification(level: str, check_type: str, message: str, details: Optional[Dict[str, Any]] = None) -> None:
    """문제가 발생했을 때 Slack 또는 Teams로 알림 전송"""
    logger.info(f"알림 전송 시도: Level={level}, Check={check_type}, Message={message}")
    success_slack = True
    success_teams = True

    # Slack
    if SLACK_WEBHOOK_URL:
        try:
            color = {'warning': '#ffcc00', 'error': '#ff0000'}.get(level, '#ff0000')
            payload = {
                "attachments": [
                    {
                        "color": color,
                        "title": f"[{level.upper()}] {check_type} 모니터링 실패",
                        "text": message + ("\n```" + json.dumps(details, indent=2) + "```" if details else ""),
                        "footer": f"Airflow Monitoring | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                    }
                ]
            }
            response = requests.post(
                SLACK_WEBHOOK_URL,
                data=json.dumps(payload),
                headers={'Content-Type': 'application/json'},
                timeout=10
            )
            if response.status_code != 200:
                logger.error(f"Slack 알림 전송 실패: {response.status_code} - {response.text}")
                success_slack = False
            else:
                logger.info("Slack 알림 전송 성공")
        except Exception as e:
            logger.error(f"Slack 알림 전송 중 오류 발생: {e}", exc_info=True)
            success_slack = False

    # MS Teams (필요시 Teams 형식에 맞게 수정)
    if TEAMS_WEBHOOK_URL:
        try:
            payload = {
                "themeColor": "FF0000" if level == 'error' else "FFCC00",
                "summary": f"{check_type} 모니터링 {level.upper()}",
                "sections": [{
                    "activityTitle": f"**[{level.upper()}] {check_type} 모니터링 실패**",
                    "activitySubtitle": message,
                    "facts": [{"name": k, "value": str(v)} for k, v in details.items()] if details else [],
                    "markdown": True
                }]
            }
            response = requests.post(
                TEAMS_WEBHOOK_URL,
                json=payload,
                timeout=10
            )
            if response.status_code >= 300: # Teams는 2xx 외에는 보통 오류
                 logger.error(f"MS Teams 알림 전송 실패: {response.status_code} - {response.text}")
                 success_teams = False
            else:
                logger.info("MS Teams 알림 전송 성공")
        except Exception as e:
            logger.error(f"MS Teams 알림 전송 중 오류 발생: {e}", exc_info=True)
            success_teams = False

    if not success_slack and not success_teams:
        logger.error("모든 알림 채널 전송 실패")
        # 알림 실패 시 스크립트 실패 처리
        sys.exit(1)

# --- 확인 함수들 ---

def check_mongo():
    """MongoDB 연결 및 상태 확인"""
    logger.info("MongoDB 상태 확인 시작...")
    try:
        # pymongo는 Worker 이미지에 설치되어 있어야 함
        from pymongo import MongoClient
        from pymongo.errors import ConnectionFailure, ConfigurationError

        if not MONGODB_URI:
            raise ValueError("MONGODB_URI 환경 변수가 설정되지 않았습니다.")

        client = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=5000, connectTimeoutMS=5000)
        # 간단한 명령으로 연결 확인
        client.admin.command('ping')
        logger.info("MongoDB 연결 성공")

        db = client[DATABASE_NAME]
        collections_to_check = {
            "news": MONGODB_NEWS_COLLECTION,
            "processed": MONGODB_PROCESSED_COLLECTION,
            # 필요한 다른 컬렉션 추가
        }
        all_db_collections = db.list_collection_names()
        logger.info(f"DB '{DATABASE_NAME}' 내 컬렉션: {all_db_collections}")

        missing_collections = []
        collection_counts = {}
        for name, col_name in collections_to_check.items():
            if col_name in all_db_collections:
                count = db[col_name].estimated_document_count() # count_documents는 느릴 수 있음
                collection_counts[col_name] = count
                logger.info(f"컬렉션 '{col_name}' 문서 수 (추정): {count}")
            else:
                missing_collections.append(col_name)

        if missing_collections:
            msg = f"필수 컬렉션 누락: {', '.join(missing_collections)}"
            logger.error(msg)
            send_notification("error", "MongoDB", msg, {"database": DATABASE_NAME, "missing": missing_collections})
            sys.exit(1) # 오류 시 종료

        logger.info("MongoDB 상태 확인 완료: 정상")

    except ImportError:
        logger.error("pymongo 라이브러리를 찾을 수 없습니다. Worker 이미지에 포함되어야 합니다.")
        send_notification("error", "MongoDB", "pymongo 라이브러리 누락")
        sys.exit(1)
    except (ConnectionFailure, ConfigurationError) as e:
        msg = f"MongoDB 연결 실패: {e}"
        logger.error(msg)
        send_notification("error", "MongoDB", msg, {"uri_used": MONGODB_URI})
        sys.exit(1)
    except Exception as e:
        msg = f"MongoDB 확인 중 예상치 못한 오류: {e}"
        logger.error(msg, exc_info=True)
        send_notification("error", "MongoDB", msg)
        sys.exit(1)
    finally:
        if 'client' in locals() and client:
            client.close()

def check_kafka():
    """Kafka 연결 및 상태 확인"""
    logger.info("Kafka 상태 확인 시작...")
    try:
        # kafka-python은 Worker 이미지에 설치되어 있어야 함
        from kafka.admin import KafkaAdminClient
        from kafka.errors import NoBrokersAvailable

        if not KAFKA_BOOTSTRAP_SERVERS:
            raise ValueError("KAFKA_BOOTSTRAP_SERVERS 환경 변수가 설정되지 않았습니다.")

        admin_client = KafkaAdminClient(
            bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
            client_id='airflow-monitoring-script',
            request_timeout_ms=5000
        )
        # 간단한 메타데이터 요청으로 연결 확인
        topics = admin_client.list_topics()
        logger.info(f"Kafka 연결 성공. 토픽 목록 확인 (일부): {list(topics)[:10]}...")

        # TODO: 필요시 특정 토픽 존재 여부 또는 컨슈머 그룹 상태 확인 로직 추가

        logger.info("Kafka 상태 확인 완료: 정상")

    except ImportError:
        logger.error("kafka-python 라이브러리를 찾을 수 없습니다. Worker 이미지에 포함되어야 합니다.")
        send_notification("error", "Kafka", "kafka-python 라이브러리 누락")
        sys.exit(1)
    except NoBrokersAvailable as e:
        msg = f"Kafka 브로커 연결 실패: {e}"
        logger.error(msg)
        send_notification("error", "Kafka", msg, {"servers_used": KAFKA_BOOTSTRAP_SERVERS})
        sys.exit(1)
    except Exception as e:
        msg = f"Kafka 확인 중 예상치 못한 오류: {e}"
        logger.error(msg, exc_info=True)
        send_notification("error", "Kafka", msg)
        sys.exit(1)
    finally:
        if 'admin_client' in locals() and admin_client:
            admin_client.close()

def check_pipeline(target_dag_id: str, max_duration_hours: int):
    """Airflow 파이프라인 DAG 상태 확인"""
    logger.info(f"파이프라인 DAG '{target_dag_id}' 상태 확인 시작...")
    try:
        # apache-airflow[postgres] 또는 psycopg2가 Worker 이미지에 설치되어 있어야 함
        from airflow.hooks.postgres_hook import PostgresHook
        from airflow.utils.state import State
        from airflow.utils.timezone import make_aware

        # Airflow 메타데이터 DB 연결 (기본 Connection ID 사용)
        # DB 연결 정보는 Pod 환경 변수(AIRFLOW__CORE__SQL_ALCHEMY_CONN 등)에서 로드됨
        pg_hook = PostgresHook(postgres_conn_id=AIRFLOW_CONN_ID)

        # 최근 성공한 DagRun 찾기
        sql_last_success = """
        SELECT execution_date, state, start_date, end_date
        FROM dag_run
        WHERE dag_id = %(dag_id)s AND state = %(state)s
        ORDER BY execution_date DESC
        LIMIT 1;
        """
        conn = pg_hook.get_conn()
        cur = conn.cursor()
        cur.execute(sql_last_success, {'dag_id': target_dag_id, 'state': State.SUCCESS})
        last_success = cur.fetchone()
        cur.close()
        conn.close()

        if not last_success:
            msg = f"DAG '{target_dag_id}'의 성공 기록이 없습니다."
            logger.warning(msg)
            send_notification("warning", "Pipeline", msg, {"target_dag_id": target_dag_id})
            # 성공 기록이 없는 것은 에러는 아닐 수 있음
            logger.info("파이프라인 상태 확인 완료: 성공 기록 없음 (경고)")
            return # 성공으로 간주하고 종료

        last_success_date = make_aware(last_success[0]) # execution_date
        last_success_end_date = make_aware(last_success[3]) if last_success[3] else None # end_date

        logger.info(f"DAG '{target_dag_id}' 마지막 성공: {last_success_date.isoformat()}, 종료: {last_success_end_date.isoformat() if last_success_end_date else 'N/A'}")

        # 마지막 성공 후 너무 오래 지났는지 확인 (예: 스케줄 간격의 2배 이상)
        # TODO: DAG의 실제 스케줄 간격을 알아내어 비교하는 로직 추가 필요 (현재는 생략)

        # 최근 실행 중인 DagRun 중 실패했거나 너무 오래 실행 중인 것이 있는지 확인
        sql_running_or_failed = """
        SELECT execution_date, state, start_date
        FROM dag_run
        WHERE dag_id = %(dag_id)s AND state IN (%(state_running)s, %(state_failed)s)
        ORDER BY execution_date DESC
        LIMIT 5; -- 최근 5개 확인
        """
        conn = pg_hook.get_conn()
        cur = conn.cursor()
        cur.execute(sql_running_or_failed, {
            'dag_id': target_dag_id,
            'state_running': State.RUNNING,
            'state_failed': State.FAILED
        })
        recent_runs = cur.fetchall()
        cur.close()
        conn.close()

        now_aware = pendulum.now(tz="UTC") # DB 시간은 보통 UTC
        max_duration = timedelta(hours=max_duration_hours)

        for run in recent_runs:
            run_date = make_aware(run[0])
            run_state = run[1]
            run_start_date = make_aware(run[2]) if run[2] else None

            if run_state == State.FAILED:
                msg = f"DAG '{target_dag_id}' 실행 실패 발견 (Execution Date: {run_date.isoformat()})"
                logger.error(msg)
                send_notification("error", "Pipeline", msg, {"target_dag_id": target_dag_id, "execution_date": run_date.isoformat()})
                sys.exit(1) # 실패 발견 시 종료

            if run_state == State.RUNNING and run_start_date:
                duration = now_aware - run_start_date
                if duration > max_duration:
                    msg = f"DAG '{target_dag_id}' 실행이 너무 오래 걸림 (Execution Date: {run_date.isoformat()}, Duration: {duration})"
                    logger.error(msg)
                    send_notification("error", "Pipeline", msg, {"target_dag_id": target_dag_id, "execution_date": run_date.isoformat(), "duration_seconds": duration.total_seconds()})
                    sys.exit(1) # 장기 실행 발견 시 종료
                else:
                     logger.info(f"DAG '{target_dag_id}' 실행 중 (Execution Date: {run_date.isoformat()}, Duration: {duration}) - 정상 범위")


        logger.info(f"파이프라인 DAG '{target_dag_id}' 상태 확인 완료: 정상")

    except ImportError:
        logger.error("Airflow 또는 DB 드라이버 라이브러리를 찾을 수 없습니다. Worker 이미지에 포함되어야 합니다.")
        send_notification("error", "Pipeline", "Airflow/DB 라이브러리 누락")
        sys.exit(1)
    except Exception as e:
        msg = f"파이프라인 상태 확인 중 예상치 못한 오류: {e}"
        logger.error(msg, exc_info=True)
        send_notification("error", "Pipeline", msg)
        sys.exit(1)


# --- 메인 실행 로직 ---
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Airflow Monitoring Check Runner")
    parser.add_argument("--check", required=True, choices=["mongo", "kafka", "pipeline"],
                        help="실행할 확인 유형")
    parser.add_argument("--target-dag-id", help="파이프라인 상태 확인 시 대상 DAG ID")
    parser.add_argument("--max-duration-hours", type=int, default=8,
                        help="파이프라인 상태 확인 시 최대 허용 실행 시간 (시간 단위)")

    args = parser.parse_args()

    logger.info(f"모니터링 확인 시작: Type={args.check}")

    if args.check == "mongo":
        check_mongo()
    elif args.check == "kafka":
        check_kafka()
    elif args.check == "pipeline":
        if not args.target_dag_id:
            logger.error("--target-dag-id 인자가 필요합니다 for pipeline check")
            sys.exit(1)
        check_pipeline(args.target_dag_id, args.max_duration_hours)
    else:
        logger.error(f"알 수 없는 확인 유형: {args.check}")
        sys.exit(1)

    logger.info(f"모니터링 확인 성공: Type={args.check}")
    sys.exit(0)
