from typing import Dict, Any, List
import asyncio
from kafka import KafkaProducer, KafkaConsumer
from pymongo import MongoClient
import json
from datetime import datetime

from .text.preprocessor import TextPreprocessor
from .topic.topic_modeler import TopicModeler
from .sentiment.analyzer import SentimentAnalyzer
from ..collectors.utils.config import NaverNewsConfig

class NewsPipeline:
    """뉴스 데이터 처리 파이프라인
    
    각 언론사별, 카테고리별로 Kafka 토픽을 생성하고
    데이터를 순차적으로 처리하는 파이프라인을 구현합니다.
    """
    
    def __init__(self):
        # Kafka 설정
        self.producer = KafkaProducer(
            bootstrap_servers=NaverNewsConfig.KAFKA_BOOTSTRAP_SERVERS,
            value_serializer=lambda x: json.dumps(x).encode('utf-8')
        )
        
        # MongoDB 설정
        self.mongo_client = MongoClient(NaverNewsConfig.MONGODB_URI)
        self.db = self.mongo_client[NaverNewsConfig.DATABASE_NAME]
        
        # 처리기 초기화
        self.text_preprocessor = TextPreprocessor()
        self.topic_modeler = TopicModeler()
        self.sentiment_analyzer = SentimentAnalyzer()
        
        # 컬렉션 인덱스 생성
        self._create_indexes()
    
    def _create_indexes(self):
        """MongoDB 컬렉션 인덱스 생성"""
        # 원본 뉴스 컬렉션
        self.db.raw_news.create_index([
            ("source", 1),
            ("category", 1),
            ("published_at", -1)
        ])
        
        # 처리된 뉴스 컬렉션
        self.db.processed_news.create_index([
            ("source", 1),
            ("category", 1),
            ("published_at", -1)
        ])
        
        # 토픽 분석 결과 컬렉션
        self.db.topic_news.create_index([
            ("source", 1),
            ("category", 1),
            ("main_topics", 1)
        ])
        
        # 감정 분석 결과 컬렉션
        self.db.sentiment_news.create_index([
            ("source", 1),
            ("category", 1),
            ("sentiment", 1)
        ])
    
    def get_topic_name(self, source: str, category: str, stage: str) -> str:
        """Kafka 토픽 이름 생성"""
        return f"news.{source}.{category}.{stage}"
    
    async def process_text(self, news_data: Dict[str, Any]) -> Dict[str, Any]:
        """텍스트 전처리"""
        processed_text = self.text_preprocessor.preprocess(news_data['content'])
        tokens = self.text_preprocessor.tokenize(processed_text)
        
        result = news_data.copy()
        result.update({
            'processed_content': processed_text,
            'tokens': tokens,
            'processed_at': datetime.now().isoformat()
        })
        
        return result
    
    async def process_topic(self, news_data: Dict[str, Any]) -> Dict[str, Any]:
        """토픽 모델링"""
        topic_result = self.topic_modeler.transform(news_data['processed_content'])
        
        result = news_data.copy()
        result.update({
            'topic_analysis': topic_result,
            'topic_processed_at': datetime.now().isoformat()
        })
        
        return result
    
    async def process_sentiment(self, news_data: Dict[str, Any]) -> Dict[str, Any]:
        """감정 분석"""
        sentiment_result = self.sentiment_analyzer.analyze(news_data['processed_content'])
        
        result = news_data.copy()
        result.update({
            'sentiment_analysis': sentiment_result,
            'sentiment_processed_at': datetime.now().isoformat()
        })
        
        return result
    
    async def process_news(self, source: str, category: str):
        """뉴스 처리 파이프라인 실행"""
        # 컨슈머 설정
        consumer = KafkaConsumer(
            self.get_topic_name(source, category, 'raw'),
            bootstrap_servers=NaverNewsConfig.KAFKA_BOOTSTRAP_SERVERS,
            value_deserializer=lambda x: json.loads(x.decode('utf-8')),
            group_id=f"news_processor_{source}_{category}"
        )
        
        try:
            for message in consumer:
                news_data = message.value
                
                # 1. 텍스트 처리
                processed_data = await self.process_text(news_data)
                self.db.processed_news.update_one(
                    {"_id": processed_data["_id"]},
                    {"$set": processed_data},
                    upsert=True
                )
                
                # Kafka로 전송
                self.producer.send(
                    self.get_topic_name(source, category, 'processed'),
                    processed_data
                )
                
                # 2. 토픽 모델링
                topic_data = await self.process_topic(processed_data)
                self.db.topic_news.update_one(
                    {"_id": topic_data["_id"]},
                    {"$set": topic_data},
                    upsert=True
                )
                
                # Kafka로 전송
                self.producer.send(
                    self.get_topic_name(source, category, 'topic'),
                    topic_data
                )
                
                # 3. 감정 분석
                sentiment_data = await self.process_sentiment(topic_data)
                self.db.sentiment_news.update_one(
                    {"_id": sentiment_data["_id"]},
                    {"$set": sentiment_data},
                    upsert=True
                )
                
                # Kafka로 전송
                self.producer.send(
                    self.get_topic_name(source, category, 'sentiment'),
                    sentiment_data
                )
                
        except Exception as e:
            print(f"Error processing news: {str(e)}")
        finally:
            consumer.close()
    
    async def run(self):
        """모든 언론사와 카테고리에 대해 처리 파이프라인 실행"""
        tasks = []
        
        # 각 언론사와 카테고리 조합에 대해 처리 태스크 생성
        for source in ['hankyung', 'mk', 'naver']:
            for category in ['economy', 'stock', 'politics', 'society', 'world', 'it']:
                task = asyncio.create_task(
                    self.process_news(source, category)
                )
                tasks.append(task)
        
        # 모든 태스크 실행
        await asyncio.gather(*tasks)
    
    def close(self):
        """리소스 정리"""
        self.producer.close()
        self.mongo_client.close()

if __name__ == "__main__":
    pipeline = NewsPipeline()
    try:
        asyncio.run(pipeline.run())
    except KeyboardInterrupt:
        print("Pipeline interrupted by user")
    finally:
        pipeline.close() 