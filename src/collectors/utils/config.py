from typing import Dict, Any
import os
from dotenv import load_dotenv

# .env 파일 로드
load_dotenv()

class NaverNewsConfig:
    # Naver API 설정
    NAVER_CLIENT_ID = os.getenv("NAVER_CLIENT_ID")
    NAVER_CLIENT_SECRET = os.getenv("NAVER_CLIENT_SECRET")
    
    # 카테고리 설정
    CATEGORIES = {
        "politics": "100",
        "economy": "101",
        "society": "102",
        "life_culture": "103",
        "it_science": "104",
        "world": "105"
    }
    
    # Kafka 설정
    KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
    KAFKA_TOPIC_NEWS_RAW = os.getenv("KAFKA_TOPIC_NEWS", "naver-news-raw")
    
    # MongoDB 설정
    MONGODB_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017/")
    DATABASE_NAME = os.getenv("DATABASE_NAME", "naver_news")
    
    # 수집 설정
    MAX_RETRIES = 3
    RETRY_DELAY = 1  # seconds
    REQUEST_DELAY = 0.5  # seconds between requests
    
    @classmethod
    def get_category_code(cls, category: str) -> str:
        return cls.CATEGORIES.get(category, "100")  # default to politics if not found 