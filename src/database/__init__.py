"""
MongoDB 데이터베이스 모듈 (비동기 중심)

이 모듈은 MongoDB 연결 및 데이터 액세스를 위한 비동기 인터페이스를 제공합니다.
"""

# 비동기 연결 및 세션 관리
from .connection import (
    connect_to_mongo,
    close_mongo_connection,
    get_database,
    create_indexes_on_startup 
)

# 기본 리포지토리 및 특정 리포지토리
from .repository import BaseRepository
from .repositories.article_repository import (
    ArticleRepository,
    RawArticleRepository,
    ProcessedArticleRepository,
    SentimentArticleRepository,
    SummaryArticleRepository
)

# 공통 예외
from .exceptions import (
    DatabaseError, 
    MongoDBConnectionError, 
    OperationError,
    NotFoundError
)

# 컬렉션 정보 (필요시)
from .collections import CollectionName, get_collection_info, CollectionInfo

__all__ = [
    # 연결 및 세션
    "connect_to_mongo",
    "close_mongo_connection",
    "get_database",
    "create_indexes_on_startup",
    
    # 저장소
    "BaseRepository",
    "ArticleRepository",
    "RawArticleRepository",
    "ProcessedArticleRepository",
    "SentimentArticleRepository",
    "SummaryArticleRepository",
    
    # 예외
    "DatabaseError",
    "MongoDBConnectionError",
    "OperationError",
    "NotFoundError",

    # 컬렉션 (선택적 익스포트)
    "CollectionName",
    "get_collection_info",
    "CollectionInfo"
] 