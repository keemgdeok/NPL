from typing import Dict, Any, List
from datetime import datetime, timedelta
import json
import time
import logging
from kafka import KafkaConsumer, KafkaProducer
from kafka.errors import NoBrokersAvailable
from pymongo import MongoClient

from .topic_modeler import KoreanTopicModeler
from ...collectors.utils.config import Config


# 로깅 설정
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class TopicProcessor:
    def __init__(self, n_topics: int = 10):
        """토픽 프로세서 초기화
        
        Args:
            n_topics: 추출할 토픽 수
        """
        # 토픽 모델러 초기화
        self.topic_modeler = KoreanTopicModeler(n_topics=n_topics)
        
        # Kafka Consumer 초기화
        self._init_kafka_consumer()
        
        # Kafka Producer 초기화
        self._init_kafka_producer()
        
        # MongoDB 설정
        self.mongo_client = MongoClient(Config.MONGODB_URI)
        self.db = self.mongo_client[Config.DATABASE_NAME]
        self.collection = self.db['topic_articles']
        
        # 인덱스 생성
        self.collection.create_index([("url", 1)], unique=True)
        self.collection.create_index([("category", 1), ("published_at", -1)])
        
        logger.info("TopicProcessor 초기화 완료")
    
    def _init_kafka_consumer(self, max_retries: int = 5):
        """Kafka Consumer 초기화 (재시도 로직 포함)"""
        retries = 0
        while retries < max_retries:
            try:
                logger.info(f"Kafka Consumer 연결 시도 중... (시도 {retries + 1}/{max_retries})")
                self.consumer = KafkaConsumer(
                    bootstrap_servers=Config.KAFKA_BOOTSTRAP_SERVERS,
                    group_id='topic_processor',
                    auto_offset_reset='latest',
                    value_deserializer=lambda x: json.loads(x.decode('utf-8')),
                    enable_auto_commit=True,
                    auto_commit_interval_ms=1000
                )
                
                # 텍스트 처리 완료된 토픽 패턴 구독
                self.consumer.subscribe(pattern=f'^{Config.KAFKA_TOPIC_PREFIX}\..*\.processed$')
                logger.info(f"Kafka Consumer 초기화 성공: 패턴 '{Config.KAFKA_TOPIC_PREFIX}.*.processed' 구독")
                break
            except NoBrokersAvailable:
                retries += 1
                sleep_time = 2 ** retries  # 지수 백오프
                logger.warning(f"Kafka 브로커에 연결할 수 없습니다. {sleep_time}초 후 재시도...")
                time.sleep(sleep_time)
                
                if retries >= max_retries:
                    logger.error("최대 재시도 횟수 초과. Kafka Consumer 초기화 실패")
                    # 배치 모드에서는 Consumer 없이도 동작 가능하므로 예외를 발생시키지 않음
                    self.consumer = None
    
    def _init_kafka_producer(self, max_retries: int = 5):
        """Kafka Producer 초기화 (재시도 로직 포함)"""
        retries = 0
        while retries < max_retries:
            try:
                logger.info(f"Kafka Producer 연결 시도 중... (시도 {retries + 1}/{max_retries})")
                self.producer = KafkaProducer(
                    bootstrap_servers=Config.KAFKA_BOOTSTRAP_SERVERS,
                    value_serializer=lambda x: json.dumps(x, default=str).encode('utf-8')
                )
                logger.info("Kafka Producer 연결 성공")
                break
            except NoBrokersAvailable:
                retries += 1
                sleep_time = 2 ** retries  # 지수 백오프
                logger.warning(f"Kafka 브로커에 연결할 수 없습니다. {sleep_time}초 후 재시도...")
                time.sleep(sleep_time)
                
                if retries >= max_retries:
                    logger.error("최대 재시도 횟수 초과. Kafka Producer 초기화 실패")
                    # 배치 모드에서는 Producer 없이도 동작 가능하므로 예외를 발생시키지 않음
                    self.producer = None
    
    def train_model(self, days: int = 30):
        """토픽 모델 학습
        
        Args:
            days: 학습에 사용할 기간 (일)
            
        Returns:
            bool: 학습 성공 여부
        """
        logger.info(f"최근 {days}일 데이터로 토픽 모델 학습 시작")
        
        # 지정된 기간 내의 기사 데이터 수집
        start_date = datetime.now() - timedelta(days=days)
        articles = self.db['processed_articles'].find(
            {"processed_at": {"$gte": start_date.isoformat()}}
        )
        
        # 학습 데이터 준비
        texts = []
        for article in articles:
            if "processed_content" in article and article["processed_content"]:
                texts.append(article["processed_content"])
        
        if len(texts) < 10:
            logger.warning(f"학습 데이터가 너무 적습니다: {len(texts)}개 (최소 10개 필요)")
            return False
            
        logger.info(f"토픽 모델 학습을 위해 {len(texts)}개의 기사를 사용합니다.")
        
        # 모델 학습
        try:
            self.topic_modeler.fit(texts)
            logger.info("토픽 모델 학습 완료")
            
            # 모델이 제대로 학습되었는지 확인
            if self.topic_modeler._model is not None and hasattr(self.topic_modeler._model, 'topics_'):
                logger.info(f"총 {len(self.topic_modeler._model.get_topics())}개의 토픽이 학습되었습니다.")
                return True
            else:
                logger.error("모델 학습 후에도 토픽이 생성되지 않았습니다.")
                return False
                
        except Exception as e:
            logger.error(f"모델 학습 중 오류 발생: {str(e)}")
            return False
    
    def process_article(self, article_data: Dict[str, Any]) -> Dict[str, Any]:
        """기사의 토픽 분석"""
        # 토픽 모델이 없으면 로드 시도
        if self.topic_modeler._model is None:
            logger.info("토픽 모델 로드 시도")
            model_loaded = self.topic_modeler.load_model()
            if not model_loaded:
                logger.info("저장된 모델이 없어 새로 학습합니다.")
                training_success = self.train_model()
                if not training_success:
                    logger.warning("모델 학습에 실패했습니다.")
        
        # 모델이 여전히 없으면 기본 응답 반환
        if self.topic_modeler._model is None or not hasattr(self.topic_modeler._model, 'topics_'):
            logger.warning("유효한 토픽 모델이 없습니다. 모델 학습이 필요합니다.")
            # 기본 응답 반환
            result = article_data.copy()
            result.update({
                "topic_analysis": {
                    "topic_id": -1,
                    "topic_prob": 0.0,
                    "topic_keywords": [],
                    "topic_distribution": [],
                    "topic_label": "모델 미학습",
                    "representative_docs": []
                },
                "topic_processed_at": datetime.now().isoformat(),
                "topic_status": "MODEL_NOT_TRAINED"
            })
            return result
        
        # 토픽 분석
        try:
            # logger.info(f"기사 토픽 분석 중: {article_data.get('title', 'Unknown Title')}")
            topic_data = self.topic_modeler.transform(article_data["processed_content"])
            
            # 주제 요약 정보 추가
            topic_summary = None
            if topic_data["topic_id"] >= 0:  # 유효한 토픽인 경우
                topic_summary = self.topic_modeler.get_topic(topic_data["topic_id"])
                
                # 대표 문서 가져오기 시도
                try:
                    representative_docs = self.topic_modeler._model.get_representative_docs(topic_data["topic_id"])
                    topic_data["representative_docs"] = representative_docs[:3] if representative_docs else []
                except Exception as e:
                    logger.warning(f"대표 문서 가져오기 실패: {str(e)}")
                    topic_data["representative_docs"] = []
            
            # 결과 데이터 생성
            result = article_data.copy()
            result.update({
                "topic_analysis": topic_data,
                "topic_processed_at": datetime.now().isoformat(),
                "topic_status": "SUCCESS"
            })
            
            return result
        except Exception as e:
            logger.error(f"토픽 분석 중 오류: {str(e)}")
            # 오류 응답 반환
            result = article_data.copy()
            result.update({
                "topic_analysis": {
                    "topic_id": -2,
                    "topic_prob": 0.0,
                    "topic_keywords": [],
                    "topic_distribution": [],
                    "topic_label": "분석 오류",
                    "error": str(e),
                    "representative_docs": []
                },
                "topic_processed_at": datetime.now().isoformat(),
                "topic_status": "ERROR"
            })
            return result
    
    def process_stream(self):
        """실시간 스트림 처리"""
        if self.consumer is None:
            logger.error("Kafka Consumer가 초기화되지 않았습니다. 스트림 처리를 시작할 수 없습니다.")
            return
            
        logger.info("토픽 분석 스트림 처리 시작")
        
        try:
            for message in self.consumer:
                try:
                    # 메시지 파싱
                    article_data = message.value
                    
                    # 기사 처리
                    processed_data = self.process_article(article_data)
                    
                    # MongoDB에 저장
                    self._save_to_mongodb(processed_data)
                    
                    # Kafka로 다음 단계 전송
                    self._send_to_kafka(processed_data)
                    
                    # logger.info(f"기사 처리 완료: {article_data.get('title', 'Unknown')}")
                    
                except Exception as e:
                    logger.error(f"기사 처리 중 오류: {str(e)}")
                    continue
        except KeyboardInterrupt:
            logger.info("사용자에 의해 스트림 처리가 중단되었습니다.")
        except Exception as e:
            logger.error(f"스트림 처리 중 오류: {str(e)}")
    
    def process_batch(self, category: str = None, days: int = 1):
        """배치 처리
        
        Args:
            category: 처리할 카테고리 (None인 경우 모든 카테고리)
            days: 처리할 기간 (일)
        """
        logger.info(f"토픽 분석 배치 처리 시작 - 카테고리: {category or '전체'}, 기간: {days}일")
        
        # 처리 기간 설정
        start_date = datetime.now() - timedelta(days=days)
        
        # 쿼리 필터 설정
        query = {"processed_at": {"$gte": start_date.isoformat()}}
        if category:
            query["category"] = category
        
        # 텍스트 처리된 기사 조회
        articles = self.db['text_articles'].find(query)
        
        # 배치 처리
        count = 0
        for article in articles:
            try:
                # 기사 처리
                processed_data = self.process_article(article)
                
                # MongoDB에 저장
                self._save_to_mongodb(processed_data)
                
                # Kafka로 전송 (Producer가 있는 경우만)
                if self.producer:
                    self._send_to_kafka(processed_data)
                
                count += 1
                if count % 100 == 0:
                    logger.info(f"{count}개 기사 처리 완료")
                    
            except Exception as e:
                logger.error(f"기사 처리 중 오류: {str(e)}")
                continue
        
        logger.info(f"배치 처리 완료 - 총 {count}개 기사 처리")
    
    def _save_to_mongodb(self, data: Dict[str, Any]):
        """MongoDB에 저장
        
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
    
    def _send_to_kafka(self, data: Dict[str, Any]):
        """Kafka로 다음 단계 전송
        
        Args:
            data: 전송할 데이터
        """
        if self.producer is None:
            logger.warning("Kafka Producer가 초기화되지 않았습니다. 메시지를 전송할 수 없습니다.")
            return
            
        try:
            # 토픽 이름 생성 (예: news.economy.topic)
            topic = f"news.{data['category']}.topic"
            
            # 카프카로 전송
            self.producer.send(topic, value=data)
        except Exception as e:
            logger.error(f"Kafka 전송 오류: {str(e)}")
    
    def close(self):
        """리소스 정리"""
        if hasattr(self, 'consumer') and self.consumer is not None:
            self.consumer.close()
            
        if hasattr(self, 'producer') and self.producer is not None:
            self.producer.flush()
            self.producer.close()
            
        if hasattr(self, 'mongo_client'):
            self.mongo_client.close()
            
        logger.info("TopicProcessor 리소스 정리 완료") 