"""
MongoDB 연결 관리

이 모듈은 MongoDB 연결 생성 및 관리 기능을 제공합니다.
"""

from typing import Optional, Dict, Any, List
import logging
import time
from functools import lru_cache

from pymongo import MongoClient
from pymongo.database import Database
from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError

from ...collectors.utils.config import Config
from .exceptions import MongoDBConnectionError

# 로깅 설정
logger = logging.getLogger(__name__)


class MongoDBConnection:
    """MongoDB 연결 관리자
    
    MongoDB 연결 생성, 관리 및 재시도 로직을 포함합니다.
    """
    
    def __init__(
        self, 
        uri: str, 
        database_name: str,
        max_retries: int = 3,
        retry_delay: int = 1,
        connection_options: Optional[Dict[str, Any]] = None
    ):
        """
        Args:
            uri: MongoDB 연결 URI
            database_name: 데이터베이스 이름
            max_retries: 연결 실패 시 최대 재시도 횟수
            retry_delay: 재시도 간 대기 시간(초)
            connection_options: MongoClient 추가 옵션
        """
        self.uri = uri
        self.database_name = database_name
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.connection_options = connection_options or {}
        self._client: Optional[MongoClient] = None
    
    @property
    def client(self) -> MongoClient:
        """연결된 MongoDB 클라이언트 반환 (필요시 연결 생성)"""
        if self._client is None:
            self._connect()
        return self._client
    
    @property
    def db(self) -> Database:
        """데이터베이스 객체 반환"""
        return self.client[self.database_name]
    
    def _connect(self) -> None:
        """MongoDB에 연결 (재시도 로직 포함)"""
        retries = 0
        last_error = None
        
        while retries < self.max_retries:
            try:
                logger.info(f"MongoDB 연결 시도 중: {self.uri}")
                self._client = MongoClient(self.uri, **self.connection_options)
                # 연결 확인
                self._client.admin.command('ping')
                logger.info(f"MongoDB {self.database_name} 연결 성공")
                return
            except (ConnectionFailure, ServerSelectionTimeoutError) as e:
                last_error = e
                retries += 1
                logger.warning(f"MongoDB 연결 실패 ({retries}/{self.max_retries}): {str(e)}")
                
                if retries < self.max_retries:
                    wait_time = self.retry_delay * (2 ** (retries - 1))  # 지수 백오프
                    logger.info(f"{wait_time}초 후 재시도...")
                    time.sleep(wait_time)
        
        # 최대 재시도 후에도 연결 실패
        logger.error("MongoDB 최대 재시도 횟수 초과")
        raise MongoDBConnectionError("MongoDB 연결 실패: 최대 재시도 횟수 초과", last_error)
    
    def create_indexes(self, collection_name: str, indexes: List) -> None:
        """컬렉션에 인덱스 생성
        
        Args:
            collection_name: 인덱스를 생성할 컬렉션 이름
            indexes: 인덱스 정의 목록 [(키, 옵션), ...]
        """
        collection = self.db[collection_name]
        for keys, options in indexes:
            index_name = collection.create_index(keys, **options)
            logger.debug(f"인덱스 생성: {index_name} (컬렉션: {collection_name})")
    
    def close(self) -> None:
        """MongoDB 연결 종료"""
        if self._client:
            self._client.close()
            self._client = None
            logger.info("MongoDB 연결 종료")
    
    def __enter__(self):
        """컨텍스트 관리자 프로토콜 지원"""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """컨텍스트 종료 시 연결 종료"""
        self.close()


@lru_cache(maxsize=1)
def get_database_connection(
    uri: Optional[str] = None, 
    database_name: Optional[str] = None,
    max_retries: Optional[int] = None,
    retry_delay: Optional[int] = None,
    **connection_options
) -> MongoDBConnection:
    """싱글톤 패턴으로 MongoDB 연결 객체 반환
    
    Args:
        uri: MongoDB 연결 URI (기본값: Config.MONGODB_URI)
        database_name: 데이터베이스 이름 (기본값: Config.DATABASE_NAME)
        max_retries: 최대 재시도 횟수 (기본값: Config.MAX_RETRIES)
        retry_delay: 재시도 간 대기 시간 (기본값: Config.RETRY_DELAY)
        connection_options: MongoClient 추가 옵션
        
    Returns:
        MongoDBConnection: MongoDB 연결 관리자 인스턴스
    """
    uri = uri or Config.MONGODB_URI
    database_name = database_name or Config.DATABASE_NAME
    max_retries = max_retries or int(Config.MAX_RETRIES)
    retry_delay = retry_delay or int(Config.RETRY_DELAY)
    
    return MongoDBConnection(
        uri=uri,
        database_name=database_name,
        max_retries=max_retries,
        retry_delay=retry_delay,
        connection_options=connection_options
    ) 