from typing import Dict, Any, List
from datetime import datetime, timedelta
import json
from kafka import KafkaConsumer, KafkaProducer
from pymongo import MongoClient

from .preprocessor import TextPreprocessor
from ...collectors.utils.config import NaverNewsConfig
from ...collectors.utils.models import NewsArticle

class TextProcessor:
    def __init__(self):
        self.preprocessor = TextPreprocessor()
        
        # Kafka 설정
        self.consumer = KafkaConsumer(
            NaverNewsConfig.KAFKA_TOPIC_NEWS_RAW,
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
        self.collection = self.db['processed_articles']
        
        # 인덱스 생성
        self.collection.create_index([("url", 1)], unique=True)
        self.collection.create_index([("category", 1), ("published_at", -1)])
    
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
            for message in self.consumer:
                try:
                    # 메시지에서 뉴스 기사 데이터 파싱
                    article_data = message.value
                    article = NewsArticle.from_dict(article_data)
                    
                    # 기사 처리
                    processed_data = self.process_article(article)
                    
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
        
        articles = self.db['news_articles'].find(query)
        
        for article_data in articles:
            try:
                article = NewsArticle.from_dict(article_data)
                processed_data = self.process_article(article)
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
                "naver-news-processed",
                value=data
            )
        except Exception as e:
            print(f"Error sending to Kafka: {str(e)}")
    
    def close(self):
        """리소스 정리"""
        self.consumer.close()
        self.producer.close()
        self.mongo_client.close() 