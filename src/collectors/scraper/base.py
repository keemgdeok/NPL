from typing import Dict, List, Optional, Any
import asyncio
import aiohttp
from abc import ABC, abstractmethod
from datetime import datetime
import logging
from kafka import KafkaProducer
import json

from ..utils.models import NewsArticle

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class BaseScraper(ABC):
    """뉴스 스크래퍼 기본 클래스
    
    모든 뉴스 스크래퍼가 구현해야 하는 기본 인터페이스를 정의합니다.
    
    Attributes:
        name (str): 스크래퍼 이름 (예: hankyung, mk, naver)
        headers (Dict[str, str]): HTTP 요청에 사용될 헤더
        categories (Dict[str, str]): 뉴스 카테고리 매핑
        producer (KafkaProducer): Kafka 프로듀서
        semaphore (asyncio.Semaphore): 동시 요청 제한을 위한 세마포어
    """
    
    def __init__(self, name: str, kafka_bootstrap_servers: str):
        self.name = name
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        # Kafka 프로듀서 설정
        self.producer = KafkaProducer(
            bootstrap_servers=kafka_bootstrap_servers,
            value_serializer=lambda x: json.dumps(x, default=str).encode('utf-8'),
            api_version=(0, 10, 2),  # 명시적 API 버전 설정
            request_timeout_ms=60000,  # 60초 타임아웃
            max_block_ms=60000,  # 메타데이터 대기 시간
            retries=5,  # 재시도 횟수
            retry_backoff_ms=1000,  # 재시도 간격 (1초)
        )
        
        # 동시 요청 제한 (기본값: 5)
        self.semaphore = asyncio.Semaphore(5)
    
    @abstractmethod
    async def get_news_content(self, session: aiohttp.ClientSession, url: str, category: str) -> Optional[NewsArticle]:
        """뉴스 기사의 내용을 수집
        
        Args:
            session (aiohttp.ClientSession): 비동기 HTTP 세션
            url (str): 수집할 뉴스 기사의 URL
            category (str): 뉴스 카테고리
            
        Returns:
            Optional[NewsArticle]: 뉴스 기사 정보 또는 None (오류 발생시)
        """
        pass
    
    @abstractmethod
    async def get_category_news(self, category: str) -> List[NewsArticle]:
        """특정 카테고리의 뉴스 목록을 수집
        
        Args:
            category (str): 수집할 뉴스 카테고리
            
        Returns:
            List[NewsArticle]: 수집된 뉴스 기사 목록
        """
        pass
    
    def send_to_kafka(self, article: NewsArticle):
        """뉴스 기사를 Kafka로 전송
        
        Args:
            article (NewsArticle): 전송할 뉴스 기사
        """
        try:
            # 토픽 이름 생성 (예: news.economy.raw)
            topic = f"news.{article.category}.raw"
            
            # Kafka로 전송
            self.producer.send(
                topic,
                value=article.to_dict()
            )
            logger.info(f"Sent to Kafka: {article.title} -> {topic}")
            
        except Exception as e:
            logger.error(f"Error sending to Kafka: {str(e)}")
    
    async def collect_all_categories(self):
        """모든 카테고리의 뉴스를 비동기로 수집"""
        # HTTP 요청 타임아웃 설정 (10초)
        timeout = aiohttp.ClientTimeout(total=10)
        async with aiohttp.ClientSession(headers=self.headers, timeout=timeout) as session:
            # 카테고리별 수집 태스크 생성
            tasks = []
            for category in self.categories.keys():
                task = asyncio.create_task(self._collect_category(session, category))
                tasks.append(task)
            
            # 모든 카테고리 동시 수집
            await asyncio.gather(*tasks, return_exceptions=True)
    
    async def _collect_category(self, session: aiohttp.ClientSession, category: str):
        """카테고리별 뉴스 수집 및 Kafka 전송"""
        try:
            articles = await self.get_category_news(category)
            for article in articles:
                self.send_to_kafka(article)
        except Exception as e:
            logger.error(f"Error collecting {category}: {str(e)}")
    
    def close(self):
        """리소스 정리"""
        self.producer.close() 