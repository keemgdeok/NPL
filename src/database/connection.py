"""
MongoDB 연결 관리 (비동기 지원)

이 모듈은 MongoDB 연결 생성 및 관리 기능을 비동기 방식으로 제공합니다.
"""

from typing import Optional, Dict, Any, List
import logging
import asyncio

import motor.motor_asyncio
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError

from .exceptions import MongoDBConnectionError

# from ...collectors.utils.config import Config

# 로깅 설정
logger = logging.getLogger(__name__)

# 전역 비동기 클라이언트 인스턴스 (애플리케이션 수명 동안 유지)
_db_client: Optional[AsyncIOMotorClient] = None
_db_instance: Optional[AsyncIOMotorDatabase] = None

async def connect_to_mongo(
    uri: str,
    database_name: str,
    max_retries: int = 3,
    retry_delay: int = 1,
    connection_options: Optional[Dict[str, Any]] = None
) -> None:
    """애플리케이션 시작 시 MongoDB에 비동기적으로 연결합니다.
    
    연결된 클라이언트와 DB 인스턴스를 전역 변수에 저장합니다.
    """
    global _db_client, _db_instance
    if _db_client:
        logger.info("MongoDB 클라이언트가 이미 연결되어 있습니다.")
        return

    connection_options = connection_options or {}

    retries = 0
    last_error = None
        
    while retries < max_retries:
        try:
            logger.info(f"MongoDB 비동기 연결 시도 중: {uri}")
            temp_client = motor.motor_asyncio.AsyncIOMotorClient(uri, **connection_options)
            await temp_client.admin.command('ping') 
            _db_client = temp_client
            _db_instance = _db_client[database_name]
            logger.info(f"MongoDB {database_name} 비동기 연결 성공")
            return
        except (ConnectionFailure, ServerSelectionTimeoutError) as e:
            last_error = e
            retries += 1
            logger.warning(f"MongoDB 비동기 연결 실패 ({retries}/{max_retries}): {str(e)}")
            if retries < max_retries:
                wait_time = retry_delay * (2 ** (retries - 1))
                logger.info(f"{wait_time}초 후 재시도...")
                await asyncio.sleep(wait_time)
    
    logger.error("MongoDB 비동기 연결 최대 재시도 횟수 초과")
    raise MongoDBConnectionError("MongoDB 비동기 연결 실패: 최대 재시도 횟수 초과", last_error)

async def close_mongo_connection() -> None:
    """애플리케이션 종료 시 MongoDB 연결을 종료합니다."""
    global _db_client
    if _db_client:
        _db_client.close()
        _db_client = None
        logger.info("MongoDB 비동기 연결 종료")

def get_database() -> AsyncIOMotorDatabase:
    """연결된 비동기 MongoDB 데이터베이스 인스턴스를 반환합니다.
    
    연결이 되어 있지 않으면 예외를 발생시킵니다.
    이 함수는 FastAPI 의존성 주입을 통해 사용될 수 있습니다.
    """
    if _db_instance is None:
        logger.error("MongoDB 데이터베이스가 연결되지 않았습니다. 앱 시작 시 connect_to_mongo()를 호출해야 합니다.")
        raise MongoDBConnectionError("MongoDB 데이터베이스가 초기화되지 않았습니다.")
    return _db_instance

async def create_indexes_on_startup() -> None:
    """애플리케이션 시작 시 필요한 컬렉션에 인덱스를 생성합니다."""
    if _db_instance is None:
        logger.warning("DB가 연결되지 않아 인덱스를 생성할 수 없습니다.")
        return

    from .collections import CollectionName, get_collection_info

    for collection_enum in CollectionName:
        collection_info = get_collection_info(collection_enum)
        if collection_info and collection_info.indexes:
            collection = _db_instance[collection_enum.value]
            logger.info(f"컬렉션 '{collection_enum.value}'에 인덱스 생성 시도...")
            for keys, options in collection_info.indexes:
                try:
                    index_name = await collection.create_index(keys, **options)
                    logger.debug(f"인덱스 생성 성공: {index_name} (컬렉션: {collection_enum.value})")
                except Exception as e:
                    logger.error(f"인덱스 '{keys}' 생성 실패 (컬렉션: {collection_enum.value}): {e}")

# --- 기존 MongoDBConnection 클래스 및 get_database_connection 함수는 제거하거나 주석 처리 --- 
# class MongoDBConnection:
#     ...

# @lru_cache(maxsize=1)
# def get_database_connection(...):
#     ... 