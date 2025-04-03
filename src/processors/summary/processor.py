from typing import Dict, Any, List
from datetime import datetime, timedelta
import json
from kafka import KafkaConsumer, KafkaProducer
from pymongo import MongoClient
import os
import logging  
import time
from .summarizer import TextSummarizer
from ...collectors.utils.config import Config

logger = logging.getLogger("summary-processor")

class SummaryProcessor:
    def __init__(self, model_path: str = None):
        # KoBART 요약 모델 사용
        self.summarizer = TextSummarizer(model_path=model_path)
        
        # Kafka 설정 - 모든 카테고리의 processed 토픽 구독 (sentiment 대신)
        processed_topics = [f"{Config.KAFKA_TOPIC_PREFIX}.{category}.processed" 
                            for category in Config.CATEGORIES.keys()]
        
        logger.info(f"구독할 토픽 목록: {processed_topics}")
        
        self.consumer = KafkaConsumer(
            *processed_topics,
            bootstrap_servers=Config.KAFKA_BOOTSTRAP_SERVERS,
            value_deserializer=lambda x: json.loads(x.decode('utf-8')),
            auto_offset_reset='latest',
            enable_auto_commit=True,
            group_id="summary-processor-group"
        )
        
        self.producer = KafkaProducer(
            bootstrap_servers=Config.KAFKA_BOOTSTRAP_SERVERS,
            value_serializer=lambda x: json.dumps(x).encode('utf-8'),
            # 타임아웃 설정 추가
            request_timeout_ms=30000,         # 30초
            max_block_ms=30000,               # 30초
            api_version_auto_timeout_ms=30000, # 30초
            # 재시도 설정
            retries=5,
            retry_backoff_ms=1000             # 1초 간격으로 재시도
        )
        
        # MongoDB 설정
        self.mongo_client = MongoClient(Config.MONGODB_URI)
        self.db = self.mongo_client[Config.DATABASE_NAME]
        self.collection = self.db['summary_articles']
        
        # 인덱스 생성
        self.collection.create_index([("url", 1)], unique=True)
        self.collection.create_index([("category", 1), ("published_at", -1)])
        self.collection.create_index([("summary_info.summary_length", 1)])
    
    def process_article(self, article_data: Dict[str, Any]) -> Dict[str, Any]:
        """기사 요약 수행
        
        Args:
            article_data: 요약할 기사 데이터
            
        Returns:
            요약 결과가 추가된 기사 데이터
        """
        # 전체 내용에 대한 요약 수행
        processed_content = article_data["processed_content"]
        
        # 3-5 문장으로 요약 생성
        summary_result = self.summarizer.summarize(
            processed_content,
            max_length=1024,  # 입력 토큰 최대 길이
            summary_max_length=0,  # 사용하지 않음 (3-5문장이 기본값)
            num_beams=5  # 빔 서치 크기 증가
        )
        
        # 제목과 요약 결합하여 키워드 추출 (옵션)
        title = article_data.get("title", "")
        summary_with_title = f"{title} {summary_result['summary']}"
        
        # 결과 데이터 생성
        result = article_data.copy()
        result.update({
            "summary_info": {
                "summary": summary_result["summary"],
                "original_length": summary_result["original_length"],
                "summary_length": summary_result["summary_length"],
                "sentence_count": summary_result.get("sentence_count", 0),  # 문장 수 정보 추가
                "compression_ratio": summary_result["summary_length"] / max(1, summary_result["original_length"]),
                "model_info": {
                    "name": "KoBART-summarization", 
                    "type": "korean text summarization"
                }
            },
            "summary_processed_at": datetime.now().isoformat()
        })
        
        return result
    
    def process_stream(self, idle_timeout_sec=None):
        """Kafka 스트림 처리
        
        Args:
            idle_timeout_sec: 이 시간(초) 동안 메시지가 없으면 자동 종료 (None이면 무한 대기)
        """
        import time
        
        last_message_time = time.time()
        message_received = False
        
        try:
            logger.info("Kafka 스트림에서 뉴스 데이터 수신 대기중...")
            
            while True:  # 무한 루프로 변경하여 타임아웃 체크 가능하게 함
                # poll을 사용하여 타임아웃 체크가 가능하도록 함
                messages = self.consumer.poll(timeout_ms=1000)  # 1초마다 체크
                
                if messages:  # 메시지가 있으면 처리
                    message_received = True
                    last_message_time = time.time()
                    
                    # 모든 파티션의 메시지 처리
                    for topic_partition, partition_messages in messages.items():
                        for message in partition_messages:
                            try:
                                # 메시지에서 기사 데이터 파싱
                                article_data = message.value
                                category = message.topic.split('.')[1]
                                
                                logger.info(f"카테고리 '{category}'의 기사 요약 중: {article_data.get('title', '제목 없음')[:30]}...")
                                
                                # 카테고리 정보가 없으면 추가
                                if 'category' not in article_data:
                                    article_data['category'] = category
                                
                                # 요약 수행
                                processed_data = self.process_article(article_data)
                                
                                # MongoDB에 저장
                                self._save_to_mongodb(processed_data)
                                
                                # 처리된 데이터를 다음 단계로 전송
                                self._send_to_kafka(processed_data, category)
                                
                                summary_length = processed_data.get('summary_info', {}).get('summary_length', 0)
                                logger.info(f"기사 요약 완료: 요약 길이 {summary_length}자")
                                
                            except Exception as e:
                                logger.error(f"메시지 처리 오류: {str(e)}", exc_info=True)
                                continue
                
                # 타임아웃 체크
                if idle_timeout_sec and message_received and (time.time() - last_message_time) > idle_timeout_sec:
                    logger.info(f"{idle_timeout_sec}초 동안 새 메시지가 없어 자동 종료합니다.")
                    break
                    
        except KeyboardInterrupt:
            logger.info("사용자에 의해 처리가 중단되었습니다")
        finally:
            self.close()
    
    def process_batch(self, category: str = None, days: int = 1):
        """MongoDB에서 데이터를 배치로 처리
        
        Args:
            category: 분석할 뉴스 카테고리
            days: 처리할 기간(일)
        """
        query = {}
        if category:
            query["category"] = category
            
        start_date = datetime.now() - timedelta(days=days)
        query["published_at"] = {"$gte": start_date.isoformat()}
        
        # 'processed_articles' 컬렉션에서 처리된 기사 가져오기 (sentiment_articles 대신)
        articles = self.db['processed_articles'].find(query)
        processed_count = 0
        
        for article_data in articles:
            try:
                processed_data = self.process_article(article_data)
                self._save_to_mongodb(processed_data)
                category = article_data.get('category', 'economy')  # 기본값 설정
                self._send_to_kafka(processed_data, category)
                processed_count += 1
                
                if processed_count % 100 == 0:
                    logger.info(f"현재까지 {processed_count}개 기사 요약 완료")
                
            except Exception as e:
                logger.error(f"기사 요약 오류: {str(e)}")
                continue
        
        logger.info(f"배치 처리 완료: 총 {processed_count}개 기사 요약됨")
    
    def _save_to_mongodb(self, data: Dict[str, Any]):
        """처리된 데이터를 MongoDB에 저장
        
        Args:
            data: 저장할 데이터
        """
        try:
            self.collection.update_one(
                {"url": data["url"]},
                {"$set": data},
                upsert=True
            )
        except Exception as e:
            logger.error(f"MongoDB 저장 오류: {str(e)}")
    
    def _send_to_kafka(self, data: Dict[str, Any], category: str):
        """처리된 데이터를 Kafka로 전송
        
        Args:
            data: 전송할 데이터
            category: 뉴스 카테고리
        """
        try:
            # 카테고리별 요약 토픽으로 전송
            topic = f"{Config.KAFKA_TOPIC_PREFIX}.{category}.summary"
            self.producer.send(topic, value=data)
            logger.debug(f"Kafka 토픽 전송 완료: {topic}")
        except Exception as e:
            logger.error(f"Kafka 전송 오류: {str(e)}")
    
    def close(self):
        """리소스 정리"""
        self.consumer.close()
        self.producer.close()
        self.mongo_client.close()
        logger.info("모든 리소스가 정리되었습니다.") 