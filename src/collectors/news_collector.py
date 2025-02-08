from typing import List, Dict, Any
from datetime import datetime
import json
from kafka import KafkaProducer
from pymongo import MongoClient

from .api.naver_news_api import NaverNewsAPICollector
from .scraper.naver_news_scraper import NaverNewsScraper
from .utils.config import NaverNewsConfig
from .utils.models import NewsArticle

class NewsCollector:
    def __init__(self):
        self.api_collector = NaverNewsAPICollector()
        self.scraper = NaverNewsScraper()
        
        # Kafka 설정
        self.producer = KafkaProducer(
            bootstrap_servers=NaverNewsConfig.KAFKA_BOOTSTRAP_SERVERS,
            value_serializer=lambda x: json.dumps(x).encode('utf-8')
        )
        
        # MongoDB 설정
        self.mongo_client = MongoClient(NaverNewsConfig.MONGODB_URI)
        self.db = self.mongo_client[NaverNewsConfig.DATABASE_NAME]
        self.collection = self.db['news_articles']
        
        # 인덱스 생성
        self.collection.create_index([("url", 1)], unique=True)
        self.collection.create_index([("category", 1), ("published_at", -1)])
    
    def collect_news(self, category: str, use_api: bool = True, days_ago: int = 1):
        """뉴스 수집 실행"""
        try:
            if use_api:
                articles = self.api_collector.collect_by_category(category)
            else:
                articles = self.scraper.scrape_news_list(category, days_ago)
            
            self._process_articles(articles, category)
            
        except Exception as e:
            print(f"Error collecting news for category {category}: {str(e)}")
    
    def collect_all_categories(self, use_api: bool = True, days_ago: int = 1):
        """모든 카테고리의 뉴스 수집"""
        for category in NaverNewsConfig.CATEGORIES.keys():
            print(f"Collecting news for category: {category}")
            self.collect_news(category, use_api, days_ago)
    
    def _process_articles(self, articles: List[NewsArticle], category: str):
        """수집된 뉴스 처리 (Kafka 전송 및 MongoDB 저장)"""
        for article in articles:
            try:
                # MongoDB에 저장
                self._save_to_mongodb(article)
                
                # Kafka로 전송
                self._send_to_kafka(article)
                
            except Exception as e:
                print(f"Error processing article: {str(e)}")
                continue
    
    def _save_to_mongodb(self, article: NewsArticle):
        """MongoDB에 뉴스 저장"""
        try:
            self.collection.update_one(
                {"url": article.url},
                {"$set": article.to_dict()},
                upsert=True
            )
        except Exception as e:
            print(f"Error saving to MongoDB: {str(e)}")
    
    def _send_to_kafka(self, article: NewsArticle):
        """Kafka로 뉴스 전송"""
        try:
            self.producer.send(
                NaverNewsConfig.KAFKA_TOPIC_NEWS_RAW,
                value=article.to_dict()
            )
        except Exception as e:
            print(f"Error sending to Kafka: {str(e)}")
    
    def close(self):
        """리소스 정리"""
        self.producer.close()
        self.mongo_client.close() 