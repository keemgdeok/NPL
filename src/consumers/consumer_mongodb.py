"""
Kafka Consumer to MongoDB Processor

이 모듈은 지정된 Kafka 토픽 패턴에서 메시지를 소비하여,
처리 후 MongoDB의 해당 컬렉션에 저장합니다.
"""

import json
import logging
import os
import signal
import re
from typing import Optional, Type

from kafka import KafkaConsumer
from kafka.errors import KafkaError
from pydantic import ValidationError

# 프로젝트 루트를 sys.path에 추가 (필요에 따라 경로 조정)
import sys
# sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.common.database.connection import get_database_connection, MongoDBConnection
from src.common.database.models import (
    ProcessedArticleModel,
    SentimentArticleModel,
    SummaryArticleModel,
    BaseModel
)
from src.common.database.repositories.article_repository import (
    ProcessedArticleRepository,
    SentimentArticleRepository,
    SummaryArticleRepository,
    ArticleRepository
)
from src.common.database.collections import CollectionName
# from src.collectors.utils.config import Config # 가정: 설정은 여기서 로드

# 로깅 설정
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO) # 로거 레벨 명시적 설정
# Kafka 클라이언트 라이브러리 로깅 레벨 설정
# logging.getLogger("kafka").setLevel(logging.DEBUG)

# --- 설정값 (Config 객체 또는 환경 변수에서 로드) ---
# 기본값은 예시이며, 실제 Config 객체 또는 환경변수에서 올바른 값을 가져오도록 해야 합니다.
KAFKA_BROKER_URL = os.getenv('KAFKA_BROKER_URLS_FOR_CONSUMER', "kafka:29092")
KAFKA_GROUP_ID = os.getenv('KAFKA_CONSUMER_GROUP_ID_MONGO', "mongo_processor_group")
# 토픽 패턴 예시: news.processed, general.processed, news.sentiment 등
# 첫 번째 세그먼트는 다양할 수 있고, 두 번째 세그먼트가 processed, sentiment, summary 중 하나인 토픽에 매칭
KAFKA_TOPIC_PATTERN = os.getenv('KAFKA_TOPIC_PATTERN_MONGO_PROCESSOR', "^news\\.[a-zA-Z0-9_-]+\\.(processed|sentiment|summary)$")
DATABASE_NAME = os.getenv('DATABASE_NAME_MONGO_PROCESSOR', "news_db")
# ----------------------------------------------------

# 실행 중 상태 플래그
running = True

def get_repository_and_model(topic: str) -> Optional[tuple[Type[ArticleRepository], Type[BaseModel], CollectionName]]:
    """
    토픽 이름에 따라 적절한 Repository, Pydantic 모델, 컬렉션 이름을 반환합니다.
    """
    match = re.fullmatch(KAFKA_TOPIC_PATTERN, topic)
    if not match:
        logger.debug(f"토픽 '{topic}'이(가) 패턴 '{KAFKA_TOPIC_PATTERN}'과 일치하지 않습니다.")
        return None

    data_type = match.group(1) # (processed|sentiment|summary)

    if data_type == "processed":
        return ProcessedArticleRepository, ProcessedArticleModel, CollectionName.PROCESSED_ARTICLES
    elif data_type == "sentiment":
        return SentimentArticleRepository, SentimentArticleModel, CollectionName.SENTIMENT_ARTICLES
    elif data_type == "summary":
        return SummaryArticleRepository, SummaryArticleModel, CollectionName.SUMMARY_ARTICLES
    else:
        # 이 경우는 정규식이 잘못되지 않는 한 발생하기 어려움
        logger.warning(f"토픽 '{topic}'에서 알 수 없는 데이터 유형 '{data_type}' 감지됨.")
        return None

def process_message(message, db_connection: MongoDBConnection):
    """
    Kafka 메시지를 처리하여 MongoDB에 저장합니다.
    """
    try:
        topic = message.topic
        logger.info(f"토픽 '{topic}'에서 메시지 수신: key={message.key}")

        repo_model_col = get_repository_and_model(topic)
        if not repo_model_col:
            return

        RepoClass, ModelClass, collection_enum_val = repo_model_col # collection_enum_val은 사용되지 않음
        
        try:
            msg_data = json.loads(message.value.decode('utf-8'))
            logger.debug(f"역직렬화된 메시지: {msg_data}")

            # 모델 클래스에 따른 데이터 전처리
            if ModelClass == SummaryArticleModel:
                if 'summary_info' in msg_data and isinstance(msg_data['summary_info'], dict) and 'summary' in msg_data['summary_info']:
                    msg_data['summary'] = msg_data['summary_info']['summary']
                else:
                    # summary_info 또는 내부 summary 키가 없을 경우, 유효성 검사에서 걸리도록 None 또는 다른 기본값 처리 가능
                    # 혹은 로깅 후 반환하여 이 메시지 처리를 건너뛸 수 있음
                    logger.warning(f"SummaryArticleModel에 필요한 'summary_info.summary' 필드가 메시지에 없습니다. 토픽: {topic}")
                    # msg_data['summary'] = None # 또는 적절한 기본값

                # processed_content는 content에서 가져옴 (이미 존재하지 않는 경우)
                if 'processed_content' not in msg_data and 'content' in msg_data:
                    msg_data['processed_content'] = msg_data['content']
                elif 'processed_content' not in msg_data:
                     logger.warning(f"SummaryArticleModel에 필요한 'processed_content' (또는 'content') 필드가 메시지에 없습니다. 토픽: {topic}")
                     # msg_data['processed_content'] = None # 또는 적절한 기본값
            
            # 다른 모델에 대한 특정 전처리 로직도 필요하다면 여기에 추가 가능
            # 예: if ModelClass == ProcessedArticleModel:
            #        if 'processed_content' not in msg_data and 'content' in msg_data:
            #            msg_data['processed_content'] = msg_data['content']

        except json.JSONDecodeError as e:
            logger.error(f"메시지 JSON 역직렬화 실패 (토픽: {topic}): {e}, 메시지 앞부분: {message.value[:200]}")
            return
        except Exception as e:
            logger.error(f"메시지 값 처리 중 알 수 없는 오류 (토픽: {topic}): {e}, 메시지 앞부분: {message.value[:200]}")
            return

        try:
            article_model = ModelClass(**msg_data)
        except ValidationError as e:
            logger.error(f"데이터 유효성 검사 실패 (토픽: {topic}, 모델: {ModelClass.__name__}): {e}, 데이터: {msg_data}")
            return
        
        repository = RepoClass() # 내부적으로 get_database_connection -> 싱글톤 DB 연결 사용

        try:
            saved_url = repository.save_article(article_model) # article_model은 Pydantic 모델 객체
            logger.info(f"'{topic}' 토픽의 기사 저장/업데이트 완료 (컬렉션: {repository.collection_name}): {saved_url}")
        except Exception as e:
            logger.error(f"DB 저장 실패 (토픽: {topic}, 컬렉션: {repository.collection_name}, URL: {getattr(article_model, 'url', 'N/A')}): {e}")

    except Exception as e:
        logger.error(f"메시지 처리 중 예기치 않은 오류 발생 (메시지 오프셋: {message.offset if message else 'N/A'}): {e}", exc_info=True)

def main():
    global running
    logger.info("Kafka to MongoDB 프로세서 시작 중...")
    logger.info(f"Kafka 브로커: {KAFKA_BROKER_URL}")
    logger.info(f"Kafka 그룹 ID: {KAFKA_GROUP_ID}")
    logger.info(f"Kafka 토픽 패턴 구독: {KAFKA_TOPIC_PATTERN}")
    logger.info(f"대상 MongoDB 데이터베이스: {DATABASE_NAME}")

    consumer = None
    db_connection_manager = None # MongoDBConnection 객체

    # Python 경로 설정 (src를 기준으로 모듈을 찾을 수 있도록)
    # 현재 파일의 디렉토리 (src/consumers)
    current_dir = os.path.dirname(os.path.abspath(__file__))
    # src 디렉토리
    src_dir = os.path.dirname(current_dir)
    # 프로젝트 루트 디렉토리 (src의 부모)
    project_root = os.path.dirname(src_dir)
    
    # sys.path에 src 디렉토리와 프로젝트 루트가 이미 포함되어 있다면 중복 추가 방지
    if src_dir not in sys.path:
        sys.path.insert(0, src_dir)
    if project_root not in sys.path:
        sys.path.insert(0, project_root)

    try:
        db_connection_manager = get_database_connection(database_name=DATABASE_NAME)
        # 첫 연결 시도 (ping)
        db_connection_manager.client.admin.command('ping')
        logger.info(f"MongoDB '{DATABASE_NAME}'에 성공적으로 연결되었습니다.")

        consumer = KafkaConsumer(
            bootstrap_servers=KAFKA_BROKER_URL.split(','),
            group_id=KAFKA_GROUP_ID,
            auto_offset_reset='earliest',
            enable_auto_commit=True, # True로 설정 시, 주기적으로 offset 자동 커밋
            # auto_commit_interval_ms=5000, # 자동 커밋 간격
            consumer_timeout_ms=1000 # 메시지가 없을 때 대기 시간 (ms)
        )
        
        

        consumer.subscribe(pattern=KAFKA_TOPIC_PATTERN)
        logger.info(f"Kafka 토픽 패턴 '{KAFKA_TOPIC_PATTERN}' 구독 시작됨.")
        # 구독된 토픽 정보 로깅 추가
        try:
            subscription = consumer.subscription()
            logger.info(f"현재 구독 정보: {subscription}")
        except Exception as e:
            logger.error(f"구독 정보 확인 중 오류 발생: {e}")

        while running:
            for message in consumer: # consumer_timeout_ms 동안 메시지 기다림
                if message:
                    process_message(message, db_connection_manager)
                if not running: # 내부 루프에서도 running 플래그 확인
                    break
            # 명시적인 메시지 처리가 없어도 루프는 consumer_timeout_ms 간격으로 돌게됨.
            # running 플래그를 확인하여 종료 로직 수행.
            if not running:
                 logger.info("Running 플래그 False 감지. 소비자 루프 종료.")
                 break
        
    except KafkaError as e:
        logger.error(f"Kafka 관련 오류 발생: {e}", exc_info=True)
    except Exception as e:
        logger.error(f"프로세서 실행 중 예상치 못한 오류 발생: {e}", exc_info=True)
    finally:
        if consumer:
            logger.info("Kafka Consumer 종료 중...")
            consumer.close()
        if db_connection_manager:
            logger.info("MongoDB 연결 종료 중...")
            db_connection_manager.close() # MongoDBConnection 클래스에 close 메서드 있음
        logger.info("Kafka to MongoDB 프로세서가 종료되었습니다.")

def signal_handler(sig, frame):
    global running
    if running: # 중복 호출 방지
        logger.info(f"종료 신호(signal {sig}) 수신. 프로세스를 안전하게 종료합니다...")
        running = False
    else:
        logger.info("이미 종료 진행 중입니다.")

if __name__ == "__main__":
    # Python 경로 설정 (src를 기준으로 모듈을 찾을 수 있도록)
    # 현재 파일의 디렉토리 (src/consumers)
    current_file_dir = os.path.dirname(os.path.abspath(__file__))
    # src 디렉토리
    src_common_dir = os.path.dirname(current_file_dir)
    # 프로젝트 루트 디렉토리 (src의 부모) - news-pipeline
    project_root_dir = os.path.dirname(src_common_dir)

    # sys.path에 프로젝트 루트가 이미 포함되어 있다면 중복 추가 방지
    if project_root_dir not in sys.path:
         sys.path.insert(0, project_root_dir)
    
    # 이제 from src.common... import 가능

    signal.signal(signal.SIGINT, signal_handler)  # Ctrl+C
    signal.signal(signal.SIGTERM, signal_handler) # kill 명령어
    
    main() 