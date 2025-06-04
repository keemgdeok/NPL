from fastapi import Depends
from motor.motor_asyncio import AsyncIOMotorDatabase
from typing import Optional

from src.database.connection import get_database as get_mongo_db
from src.database.repositories.article_repository import (
    ArticleRepository,
    RawArticleRepository,
    ProcessedArticleRepository,
    SentimentArticleRepository,
    SummaryArticleRepository
)
# from src.api.db.mongodb_handler import Database # Database 클래스 import 제거 (더 이상 사용 안 함)

# _db_handler_instance: Optional[Database] = None # 관련 변수 제거

# async def get_db_handler() -> Database: # 함수 전체 주석 또는 삭제
#     """기존 Database 클래스 인스턴스를 반환하는 임시 의존성 함수입니다."""
#     global _db_handler_instance
#     if _db_handler_instance is None:
#         _db_handler_instance = Database()
#     return _db_handler_instance

async def get_db_session() -> AsyncIOMotorDatabase:
    """
    비동기 MongoDB 데이터베이스 세션을 반환하는 의존성입니다.
    FastAPI Depends와 함께 사용됩니다.
    """
    # get_mongo_db()는 이미 비동기 함수 connect_to_mongo를 통해 설정된
    # _db_instance를 반환하므로, 여기서 await get_mongo_db()를 호출할 필요가 없습니다.
    # get_database() 함수 자체가 동기 함수입니다.
    # 그러나, get_mongo_db (즉, get_database)의 반환값이 AsyncIOMotorDatabase 이므로
    # 이 함수 시그니처는 async def로 유지하는 것이 FastAPI의 Depends와 더 잘 맞습니다.
    # 실제 DB 호출은 Repository 레벨에서 await를 사용합니다.
    return get_mongo_db() # await 제거

# Repository 의존성 주입 함수들
async def get_article_repository(
    db_session: AsyncIOMotorDatabase = Depends(get_db_session)
) -> ArticleRepository:
    """ArticleRepository 인스턴스를 반환하는 의존성입니다."""
    return ArticleRepository(db_session=db_session)

async def get_raw_article_repository(
    db_session: AsyncIOMotorDatabase = Depends(get_db_session)
) -> RawArticleRepository:
    """RawArticleRepository 인스턴스를 반환하는 의존성입니다."""
    return RawArticleRepository(db_session=db_session)

async def get_processed_article_repository(
    db_session: AsyncIOMotorDatabase = Depends(get_db_session)
) -> ProcessedArticleRepository:
    """ProcessedArticleRepository 인스턴스를 반환하는 의존성입니다."""
    return ProcessedArticleRepository(db_session=db_session)

async def get_sentiment_article_repository(
    db_session: AsyncIOMotorDatabase = Depends(get_db_session)
) -> SentimentArticleRepository:
    """SentimentArticleRepository 인스턴스를 반환하는 의존성입니다."""
    return SentimentArticleRepository(db_session=db_session)

async def get_summary_article_repository(
    db_session: AsyncIOMotorDatabase = Depends(get_db_session)
) -> SummaryArticleRepository:
    """SummaryArticleRepository 인스턴스를 반환하는 의존성입니다."""
    return SummaryArticleRepository(db_session=db_session)

# # 주석 처리된 기존 get_db_handler 관련 코드가 있다면 삭제합니다. (두 번째 get_db_handler 정의)
# async def get_db_handler(): 
#     """MongoDB Database 핸들러 인스턴스를 생성하고 제공(yield)합니다.
#     ...
#     """
#     db = Database()
#     try:
#         yield db
#     finally:
#         db.close() 