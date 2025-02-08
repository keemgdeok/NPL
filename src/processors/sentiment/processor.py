from typing import Dict, Any, List
from datetime import datetime, timedelta
import json
from kafka import KafkaConsumer, KafkaProducer
from pymongo import MongoClient

from .analyzer import SentimentAnalyzer
from ..text.preprocessor import TextPreprocessor
from ...collectors.utils.config import NaverNewsConfig

class SentimentProcessor:
    def __init__(self):
        self.analyzer = SentimentAnalyzer()
        self.text_preprocessor = TextPreprocessor()
        
        # Kafka 설정
        self.consumer = KafkaConsumer(
            "naver-news-topics",
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
        self.collection = self.db['sentiment_articles']
        
        # 인덱스 생성
        self.collection.create_index([("url", 1)], unique=True)
        self.collection.create_index([("category", 1), ("published_at", -1)])
        self.collection.create_index([("sentiment.sentiment", 1)])
    
    def process_article(self, article_data: Dict[str, Any]) -> Dict[str, Any]:
        """기사의 감정 분석"""
        # 전체 내용에 대한 감정 분석
        content_sentiment = self.analyzer.analyze(article_data["processed_content"])
        
        # 토큰화된 단어들 가져오기
        tokens = self.text_preprocessor.tokenize(article_data["processed_content"])
        
        # 감정별 키워드 추출
        sentiment_keywords = self.analyzer.get_sentiment_keywords(
            article_data["processed_content"],
            tokens
        )
        
        # 결과 데이터 생성
        result = article_data.copy()
        result.update({
            "sentiment_analysis": {
                "overall_sentiment": content_sentiment,
                "sentiment_keywords": sentiment_keywords
            },
            "sentiment_processed_at": datetime.now().isoformat()
        })
        
        return result
    
    def process_stream(self):
        """Kafka 스트림 처리"""
        try:
            for message in self.consumer:
                try:
                    # 메시지에서 기사 데이터 파싱
                    article_data = message.value
                    
                    # 감정 분석
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
        
        articles = self.db['topic_articles'].find(query)
        
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
                "naver-news-analyzed",
                value=data
            )
        except Exception as e:
            print(f"Error sending to Kafka: {str(e)}")
    
    def close(self):
        """리소스 정리"""
        self.consumer.close()
        self.producer.close()
        self.mongo_client.close() 