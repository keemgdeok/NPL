from typing import Dict, Any, List
from datetime import datetime, timedelta
import json
from kafka import KafkaConsumer, KafkaProducer
from pymongo import MongoClient

from .topic_modeler import TopicModeler
from ...collectors.utils.config import NaverNewsConfig
from ...collectors.utils.models import NewsArticle

class TopicProcessor:
    def __init__(self, n_topics: int = 10):
        self.topic_modeler = TopicModeler(n_topics=n_topics)
        
        # Kafka 설정
        self.consumer = KafkaConsumer(
            "naver-news-processed",
            bootstrap_servers=NaverNewsConfig.KAFKA_BOOTSTRAP_SERVERS,
            value_deserializer=lambda x: json.loads(x.decode('utf-8')),
            auto_offset_reset='latest',
            enable_auto_commit=True
        )
        
        self.producer = KafkaProducer(
            bootstrap_servers=NaverNewsConfig.KAFKA_BOOTSTRAP_SERVERS,
            value_serializer=lambda x: json.dumps(x).encode('utf-8')
        )
        
        # MongoDB 설정
        self.mongo_client = MongoClient(NaverNewsConfig.MONGODB_URI)
        self.db = self.mongo_client[NaverNewsConfig.DATABASE_NAME]
        self.collection = self.db['topic_articles']
        
        # 인덱스 생성
        self.collection.create_index([("url", 1)], unique=True)
        self.collection.create_index([("category", 1), ("published_at", -1)])
    
    def train_model(self, days: int = 30):
        """최근 데이터로 토픽 모델 학습"""
        # 학습 데이터 가져오기
        start_date = datetime.now() - timedelta(days=days)
        articles = self.db['processed_articles'].find({
            "published_at": {"$gte": start_date.isoformat()}
        })
        
        # 텍스트 데이터 준비
        texts = [article["processed_content"] for article in articles]
        
        if texts:
            # 모델 학습
            print(f"Training topic model with {len(texts)} articles...")
            self.topic_modeler.fit(texts)
            print("Topic model training completed")
        else:
            print("No articles found for training")
    
    def process_article(self, article_data: Dict[str, Any]) -> Dict[str, Any]:
        """기사의 토픽 분석"""
        # 토픽 모델이 없으면 로드 시도
        if not hasattr(self.topic_modeler, 'lda'):
            if not self.topic_modeler.load_model():
                self.train_model()
        
        # 토픽 분석
        topic_data = self.topic_modeler.transform(article_data["processed_content"])
        
        # 결과 데이터 생성
        result = article_data.copy()
        result.update({
            "topic_analysis": topic_data,
            "topic_processed_at": datetime.now().isoformat()
        })
        
        return result
    
    def process_stream(self):
        """Kafka 스트림 처리"""
        try:
            for message in self.consumer:
                try:
                    # 메시지에서 기사 데이터 파싱
                    article_data = message.value
                    
                    # 토픽 분석
                    processed_data = self.process_article(article_data)
                    
                    # MongoDB에 저장
                    self._save_to_mongodb(processed_data)
                    
                    # 처리된 데이터를 다음 단계로 전송
                    self._send_to_kafka(processed_data)
                    
                except Exception as e:
                    print(f"Error processing message: {str(e)}")
                    continue
                    
        except KeyboardInterrupt:
            print("Processing interrupted by user")
        finally:
            self.close()
    
    def process_batch(self, category: str = None, days: int = 1):
        """MongoDB에서 데이터를 배치로 처리"""
        query = {}
        if category:
            query["category"] = category
            
        start_date = datetime.now() - timedelta(days=days)
        query["published_at"] = {"$gte": start_date.isoformat()}
        
        articles = self.db['processed_articles'].find(query)
        
        for article_data in articles:
            try:
                processed_data = self.process_article(article_data)
                self._save_to_mongodb(processed_data)
                self._send_to_kafka(processed_data)
            except Exception as e:
                print(f"Error processing article: {str(e)}")
                continue
    
    def _save_to_mongodb(self, data: Dict[str, Any]):
        """처리된 데이터를 MongoDB에 저장"""
        try:
            self.collection.update_one(
                {"url": data["url"]},
                {"$set": data},
                upsert=True
            )
        except Exception as e:
            print(f"Error saving to MongoDB: {str(e)}")
    
    def _send_to_kafka(self, data: Dict[str, Any]):
        """처리된 데이터를 Kafka로 전송"""
        try:
            self.producer.send(
                "naver-news-topics",
                value=data
            )
        except Exception as e:
            print(f"Error sending to Kafka: {str(e)}")
    
    def close(self):
        """리소스 정리"""
        self.consumer.close()
        self.producer.close()
        self.mongo_client.close() 