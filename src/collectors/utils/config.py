from typing import Dict
import os
from dotenv import load_dotenv

# .env 파일 로드
load_dotenv()

class Config:
    """애플리케이션 전체 설정"""
    
    # Kafka 설정
    KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
    KAFKA_TOPIC_PREFIX = os.getenv("KAFKA_TOPIC_PREFIX", "news")
    
    # MongoDB 설정
    MONGODB_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017/")
    DATABASE_NAME = os.getenv("DATABASE_NAME", "news_db")
    
    # AWS 설정
    AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
    AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
    AWS_REGION = os.getenv("AWS_REGION", "ap-northeast-2")
    S3_BUCKET_NAME = os.getenv("S3_BUCKET_NAME", "news-archive")
    
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
    MAX_RETRIES = int(os.getenv("MAX_RETRIES", "3"))
    RETRY_DELAY = int(os.getenv("RETRY_DELAY", "1"))
    REQUEST_DELAY = float(os.getenv("REQUEST_DELAY", "0.5"))
    
    # 저장소 설정
    STORAGE_BATCH_SIZE = int(os.getenv("STORAGE_BATCH_SIZE", "50"))
    STORAGE_FLUSH_INTERVAL = int(os.getenv("STORAGE_FLUSH_INTERVAL", "60"))
    STORAGE_MAX_WORKERS = int(os.getenv("STORAGE_MAX_WORKERS", "5"))
    
    @classmethod
    def validate(cls):
        """필수 환경 변수 검증"""
        required_vars = [
            "AWS_ACCESS_KEY_ID",
            "AWS_SECRET_ACCESS_KEY",
            "MONGODB_URI"
        ]
        
        missing_vars = [var for var in required_vars if not getattr(cls, var)]
        if missing_vars:
            raise ValueError(f"필수 환경 변수가 설정되지 않았습니다: {', '.join(missing_vars)}")
    
    @classmethod
    def get_category_code(cls, category: str) -> str:
        """카테고리 코드 조회"""
        return cls.CATEGORIES.get(category, "100")  # default to politics if not found 