from typing import Dict
import os
from dotenv import load_dotenv

# 공통 설정에서 SHARED_CATEGORIES 가져오기
from src.common.config import SHARED_CATEGORIES

# .env 파일 로드
load_dotenv()

class Config:
    """애플리케이션 전체 설정"""
    
    # 로깅 레벨 설정 (환경 변수 LOG_LEVEL 사용, 없으면 "INFO")
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
    
    # Kafka 설정
    KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
    KAFKA_TOPIC_PREFIX = os.getenv("KAFKA_TOPIC_PREFIX", "news")
    
    # 뉴스 카테고리 설정 (src.common.config에서 가져옴)
    CATEGORIES: Dict[str, str] = SHARED_CATEGORIES
    
    # 수집 설정
    MAX_RETRIES = int(os.getenv("MAX_RETRIES", "3"))
    RETRY_DELAY = int(os.getenv("RETRY_DELAY", "1"))
    REQUEST_DELAY = float(os.getenv("REQUEST_DELAY", "0.5"))
    
    
    @classmethod
    def validate(cls):
        """필수 환경 변수 검증"""
        required_vars = [
            # "MONGODB_URI"
        ]
        
        # S3 기능을 사용하는 컴포넌트에서만 AWS 자격증명 검사
        component_name = os.getenv("COMPONENT_NAME", "")
        if "collector" in component_name.lower() and "s3" in component_name.lower():
            required_vars.extend(["AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY"])
        
        missing_vars = [var for var in required_vars if not getattr(cls, var)]
        if missing_vars:
            raise ValueError(f"필수 환경 변수가 설정되지 않았습니다: {', '.join(missing_vars)}")
    
    @classmethod
    def get_category_code(cls, category: str) -> str:
        """카테고리 코드 조회"""
        return cls.CATEGORIES.get(category, "100")  # default to politics if not found 