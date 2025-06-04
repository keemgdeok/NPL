from pydantic_settings import BaseSettings
from typing import Optional, Dict, List

# 공통 설정에서 CATEGORIES 가져오기
from src.common.config import SHARED_CATEGORIES

class Settings(BaseSettings):
    PROJECT_NAME: str = "News Pipeline API"
    API_V1_STR: str = "/api/v1"

    # 데이터베이스 설정 (환경 변수 또는 .env 파일에서 로드)
    DATABASE_URL: Optional[str] = "mongodb://localhost:27017/" # MongoDB URL 예시
    # DATABASE_URL: Optional[str] = "sqlite:///./test.db" # 기존 예시 주석 처리
    MONGO_DATABASE_NAME: str = "news_db" # MongoDB 데이터베이스 이름
    MONGO_MAX_RETRIES: int = 3             # MongoDB 연결 최대 재시도 횟수
    MONGO_RETRY_DELAY: int = 1             # MongoDB 재시도 간 대기 시간(초)

    # 뉴스 카테고리 설정 (src.common.config에서 가져옴)
    CATEGORIES: Dict[str, str] = SHARED_CATEGORIES
    
    # 사용 가능한 카테고리 키 목록 (라우터 등에서 활용)
    @property
    def CATEGORY_KEYS(self) -> List[str]:
        return list(self.CATEGORIES.keys())

    # JWT 설정 (필요시 주석 해제 및 값 설정)
    # SECRET_KEY: str = "your-secret-key"
    # ALGORITHM: str = "HS256"
    # ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    # 로깅 레벨 설정 추가
    LOG_LEVEL: str = "INFO" # 환경 변수 LOG_LEVEL로 오버라이드 가능

    class Config:
        env_file = ".env"
        env_file_encoding = 'utf-8'

settings = Settings() 