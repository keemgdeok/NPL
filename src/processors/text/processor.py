from typing import Dict, Any, List
from datetime import datetime, timedelta
import json
from kafka import KafkaConsumer, KafkaProducer
import time
import logging

from .preprocessor import TextPreprocessor
from ...collectors.utils.config import Config
from ...collectors.utils.models import NewsArticle
from ...common.database.repositories.article_repository import ProcessedArticleRepository

# 로깅 설정
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class TextProcessor:
    def __init__(self):
        self.preprocessor = TextPreprocessor()
        
        # Repository 초기화
        self.repository = ProcessedArticleRepository()
        
        # Kafka 연결 재시도 설정
        retries = 0
        max_retries = 5
        while retries < max_retries:
            try:
                logger.info(f"Kafka 연결 시도 중... (시도 {retries + 1}/{max_retries})")
                logger.info(f"Kafka 서버 주소: {Config.KAFKA_BOOTSTRAP_SERVERS}")
                
                # Kafka Consumer 설정
                self.consumer = KafkaConsumer(
                    bootstrap_servers=Config.KAFKA_BOOTSTRAP_SERVERS,
                    value_deserializer=lambda x: json.loads(x.decode('utf-8')),
                    auto_offset_reset='latest',
                    enable_auto_commit=True,
                    group_id='text_processor_group',
                    session_timeout_ms=60000,
                    request_timeout_ms=70000,
                    connections_max_idle_ms=540000,
                    max_poll_interval_ms=600000
                )
                
                # 패턴 구독 설정
                self.consumer.subscribe(pattern=f'^{Config.KAFKA_TOPIC_PREFIX}\..*\.raw$')
                logger.info("Kafka Consumer 초기화 성공")
                break
                
            except Exception as e:
                logger.error(f"Kafka 연결 실패: {str(e)}")
                retries += 1
                if retries < max_retries:
                    wait_time = 5 * retries  # 점진적으로 대기 시간 증가
                    logger.info(f"{wait_time}초 후 재시도...")
                    time.sleep(wait_time)
                else:
                    logger.error("최대 재시도 횟수 초과")
                    raise
        
        # Kafka Producer 설정
        self.producer = KafkaProducer(
            bootstrap_servers=Config.KAFKA_BOOTSTRAP_SERVERS,
            value_serializer=lambda x: json.dumps(x).encode('utf-8')
        )
    
    def process_article(self, article: NewsArticle) -> Dict[str, Any]:
        """뉴스 기사 처리"""
        # 1. 텍스트 전처리
        processed_content = self.preprocessor.preprocess(article.content)
        
        # 2. 키워드 추출
        keywords = self.preprocessor.extract_keywords(processed_content)
        
        # 3. 처리된 데이터 생성
        processed_data = article.to_dict()
        processed_data.update({
            "processed_content": processed_content,
            "keywords": keywords,
            "processed_at": datetime.now().isoformat()
        })
        
        return processed_data
    
    def process_stream(self):
        """Kafka 스트림 처리"""
        try:
            logger.info("메시지 처리 대기 중...")
            for message in self.consumer:
                try:
                    # 메시지에서 뉴스 기사 데이터 파싱
                    article_data = message.value
                    logger.info(f"메시지 수신: {article_data.get('title', 'Unknown Title')} (토픽: {message.topic})")
                    
                    article = NewsArticle.from_dict(article_data)
                    
                    # 기사 처리
                    processed_data = self.process_article(article)
                    logger.info(f"기사 처리 완료: {processed_data['title']}")
                    
                    # MongoDB에 저장 (Repository 패턴 사용)
                    self.repository.save_article(processed_data)
                    logger.info(f"MongoDB 저장 완료: {processed_data['title']}")
                    
                    # 처리된 데이터를 다음 단계로 전송
                    self._send_to_kafka(processed_data)
                    logger.info(f"Kafka 전송 완료: {processed_data['title']} -> naver-news-processed")
                    
                except Exception as e:
                    logger.error(f"메시지 처리 중 오류 발생: {str(e)}")
                    continue
                    
        except KeyboardInterrupt:
            logger.info("사용자에 의해 처리가 중단되었습니다.")
        finally:
            self.close()
    
    def process_batch(self, category: str = None, days: int = 1):
        """MongoDB에서 데이터를 배치로 처리"""
        from ...common.database.repositories.article_repository import RawArticleRepository
        
        raw_repo = RawArticleRepository()
        
        if category:
            articles = raw_repo.get_articles_by_category(category, days=days)
        else:
            # 모든 카테고리 처리
            articles = []
            for category in Config.CATEGORIES.keys():
                articles.extend(raw_repo.get_articles_by_category(category, days=days))
        
        for article_data in articles:
            try:
                article = NewsArticle.from_dict(article_data)
                processed_data = self.process_article(article)
                self.repository.save_article(processed_data)
                self._send_to_kafka(processed_data)
                logger.info(f"배치 처리 완료: {processed_data['title']}")
            except Exception as e:
                logger.error(f"기사 처리 오류: {str(e)}")
                continue
    
    def _send_to_kafka(self, data: Dict[str, Any]):
        """처리된 데이터를 Kafka로 전송"""
        try:
            # 토픽 이름 생성 (예: news.economy.processed)
            topic = f"news.{data['category']}.processed"
            
            # Kafka로 전송
            self.producer.send(
                topic,
                value=data
            )
            logger.info(f"Sent to Kafka: {data['title']} -> {topic}")
            
        except Exception as e:
            logger.error(f"Error sending to Kafka: {str(e)}")
    
    def close(self):
        """리소스 정리"""
        self.consumer.close()
        self.producer.close()
        # Repository는 자동으로 정리됨

    def process_stream_once(self):
        """스트림에서 메시지를 한 번만 처리하고 종료"""
        logger.info("일회성 메시지 처리를 시작합니다...")
        
        # 타임아웃 설정 (예: 30초)
        messages = self.consumer.poll(timeout_ms=30000)
        
        if not messages:
            logger.info("처리할 메시지가 없습니다.")
            return
        
        logger.info(f"{sum(len(records) for records in messages.values())}개의 메시지를 처리합니다.")
        
        # 메시지 처리
        for tp, records in messages.items():
            for record in records:
                try:
                    # 메시지에서 뉴스 기사 데이터 파싱
                    article_data = record.value
                    logger.info(f"메시지 수신: {article_data.get('title', 'Unknown Title')} (토픽: {record.topic})")
                    
                    article = NewsArticle.from_dict(article_data)
                    
                    # 기사 처리
                    processed_data = self.process_article(article)
                    logger.info(f"기사 처리 완료: {processed_data['title']}")
                    
                    # MongoDB에 저장
                    self.repository.save_article(processed_data)
                    logger.info(f"MongoDB 저장 완료: {processed_data['title']}")
                    
                    # 처리된 데이터를 다음 단계로 전송
                    self._send_to_kafka(processed_data)
                    logger.info(f"Kafka 전송 완료: {processed_data['title']} -> news.{processed_data['category']}.processed")
                    
                except Exception as e:
                    logger.error(f"메시지 처리 중 오류 발생: {str(e)}")
                    continue
        
        # 처리한 offset commit
        self.consumer.commit()
        logger.info("일회성 메시지 처리를 완료했습니다.") 