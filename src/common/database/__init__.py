"""
MongoDB 데이터베이스 모듈

이 모듈은 MongoDB 연결 및 데이터 액세스를 위한 공통 인터페이스를 제공합니다.
"""

from .connection import MongoDBConnection, get_database_connection
from .repository import BaseRepository
from .exceptions import DatabaseError, MongoDBConnectionError, OperationError
from .repositories.article_repository import (
    RawArticleRepository,
    ProcessedArticleRepository,
    SentimentArticleRepository,
    SummaryArticleRepository
)

__all__ = [
    # 연결 관리
    "MongoDBConnection",
    "get_database_connection",
    
    # 저장소
    "BaseRepository",
    "RawArticleRepository",
    "ProcessedArticleRepository",
    "SentimentArticleRepository",
    "SummaryArticleRepository",
    
    # 예외
    "DatabaseError",
    "MongoDBConnectionError",
    "OperationError"
] 