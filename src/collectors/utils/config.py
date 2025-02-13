from typing import Dict
import os
from dotenv import load_dotenv

# .env 파일 로드
load_dotenv()

class Config:
    """애플리케이션 전체 설정"""
    
    # Kafka 설정
    KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
    
    # MongoDB 설정
    MONGODB_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017/")
    DATABASE_NAME = os.getenv("DATABASE_NAME", "news_db")
    
    # API 설정
    API_HOST = os.getenv("API_HOST", "0.0.0.0")
    API_PORT = int(os.getenv("API_PORT", "8000"))
    
    # 로깅 설정
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
    
    # 뉴스 카테고리 설정
    CATEGORIES: Dict[str, str] = {
        "economy": "경제",
        "business": "기업",
        "society": "사회",
        "world": "국제",
        "politics": "정치",
        "it": "IT",
        "culture": "문화"
    }
    
    # 수집 설정
    MAX_RETRIES = 3
    RETRY_DELAY = 1  # seconds
    REQUEST_DELAY = 0.5  # seconds between requests

    @classmethod
    def get_category_code(cls, category: str) -> str:
        return cls.CATEGORIES.get(category, "100")  # default to politics if not found 