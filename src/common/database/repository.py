"""
MongoDB 데이터 액세스 Repository 패턴 구현

이 모듈은 MongoDB 컬렉션에 대한 CRUD 작업을 추상화하는 Repository 클래스를 제공합니다.
"""

from typing import Dict, List, Any, Optional, Generic, TypeVar, Type, Union, Tuple, cast
from datetime import datetime
import logging

from pymongo.collection import Collection
from pymongo.errors import PyMongoError
from bson import ObjectId

from .connection import get_database_connection
from .collections import CollectionName, get_collection_indexes, get_collection_info
from .exceptions import OperationError

# 로깅 설정
logger = logging.getLogger(__name__)

# 제네릭 타입 변수
T = TypeVar('T')


class BaseRepository(Generic[T]):
    """MongoDB 기본 저장소 클래스
    
    일반적인 CRUD 작업을 제공하는 기본 Repository 구현입니다.
    컬렉션별 특화 기능이 필요한 경우 이 클래스를 상속하여 확장할 수 있습니다.
    """
    
    def __init__(
        self, 
        collection_name: Union[str, CollectionName],
        create_indexes: bool = True
    ):
        """
        Args:
            collection_name: 컬렉션 이름 또는 CollectionName 열거형
            create_indexes: 시작 시 인덱스 생성 여부
        """
        # 문자열 또는 열거형에서 컬렉션 이름 추출
        if isinstance(collection_name, CollectionName):
            self.collection_name = collection_name.value
            self.collection_enum = collection_name
        else:
            self.collection_name = collection_name
            try:
                self.collection_enum = CollectionName(collection_name)
            except ValueError:
                self.collection_enum = None
            
        # 데이터베이스 연결
        self.db_conn = get_database_connection()
        self.collection: Collection = self.db_conn.db[self.collection_name]
        
        # 인덱스 생성 (필요시)
        if create_indexes:
            if self.collection_enum:
                # 새로운 인덱스 관리 방식 사용
                collection_info = get_collection_info(self.collection_enum)
                if collection_info and collection_info.indexes:
                    for keys, options in collection_info.indexes:
                        self.collection.create_index(keys, **options)
            else:
                # 이전 방식 폴백 - get_collection_indexes 함수 사용
                indexes = get_collection_indexes(self.collection_name)
                if indexes:
                    for keys, options in indexes:
                        self.collection.create_index(keys, **options)
    
    def find_one(
        self, 
        query: Dict[str, Any],
        projection: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict[str, Any]]:
        """단일 문서 조회
        
        Args:
            query: 조회 조건
            projection: 반환할 필드 지정
            
        Returns:
            Optional[Dict]: 조회된 문서 또는 None
            
        Raises:
            OperationError: 조회 작업 실패 시
        """
        try:
            return self.collection.find_one(query, projection)
        except PyMongoError as e:
            logger.error(f"단일 문서 조회 실패: {str(e)}")
            raise OperationError("find_one", self.collection_name, query, e)
    
    def find_many(
        self, 
        query: Dict[str, Any] = None, 
        projection: Optional[Dict[str, Any]] = None,
        sort_key: Optional[Union[str, List[Tuple[str, int]]]] = None,
        sort_order: int = -1,
        skip: int = 0, 
        limit: int = 0
    ) -> List[Dict[str, Any]]:
        """여러 문서 조회
        
        Args:
            query: 조회 조건
            projection: 반환할 필드 지정
            sort_key: 정렬 기준 필드 또는 (필드, 방향) 튜플 목록
            sort_order: 정렬 방향 (1: 오름차순, -1: 내림차순)
            skip: 건너뛸 문서 수
            limit: 최대 반환 문서 수
            
        Returns:
            List[Dict]: 조회된 문서 목록
            
        Raises:
            OperationError: 조회 작업 실패 시
        """
        try:
            query = query or {}
            cursor = self.collection.find(query, projection)
            
            # 정렬 적용
            if sort_key:
                if isinstance(sort_key, str):
                    cursor = cursor.sort(sort_key, sort_order)
                else:
                    cursor = cursor.sort(sort_key)
            
            # 페이지네이션 적용
            if skip:
                cursor = cursor.skip(skip)
            
            if limit:
                cursor = cursor.limit(limit)
                
            return list(cursor)
        except PyMongoError as e:
            logger.error(f"다중 문서 조회 실패: {str(e)}")
            raise OperationError("find_many", self.collection_name, query, e)
    
    def count(self, query: Dict[str, Any] = None) -> int:
        """문서 개수 조회
        
        Args:
            query: 조회 조건
            
        Returns:
            int: 조회된 문서 개수
            
        Raises:
            OperationError: 조회 작업 실패 시
        """
        try:
            query = query or {}
            return self.collection.count_documents(query)
        except PyMongoError as e:
            logger.error(f"문서 개수 조회 실패: {str(e)}")
            raise OperationError("count", self.collection_name, query, e)
    
    def insert_one(self, document: Dict[str, Any]) -> str:
        """단일 문서 삽입
        
        Args:
            document: 삽입할 문서
            
        Returns:
            str: 삽입된 문서의 ID
            
        Raises:
            OperationError: 삽입 작업 실패 시
        """
        try:
            result = self.collection.insert_one(document)
            return str(result.inserted_id)
        except PyMongoError as e:
            logger.error(f"단일 문서 삽입 실패: {str(e)}")
            raise OperationError("insert_one", self.collection_name, None, e)
    
    def insert_many(self, documents: List[Dict[str, Any]]) -> List[str]:
        """여러 문서 삽입
        
        Args:
            documents: 삽입할 문서 목록
            
        Returns:
            List[str]: 삽입된 문서의 ID 목록
            
        Raises:
            OperationError: 삽입 작업 실패 시
        """
        try:
            result = self.collection.insert_many(documents)
            return [str(id) for id in result.inserted_ids]
        except PyMongoError as e:
            logger.error(f"다중 문서 삽입 실패: {str(e)}")
            raise OperationError("insert_many", self.collection_name, None, e)
    
    def update_one(
        self, 
        query: Dict[str, Any], 
        update_data: Dict[str, Any],
        upsert: bool = False
    ) -> int:
        """단일 문서 업데이트
        
        Args:
            query: 업데이트할 문서 조회 조건
            update_data: 업데이트할 데이터
            upsert: 문서가 없을 경우 삽입 여부
            
        Returns:
            int: 업데이트된 문서 수
            
        Raises:
            OperationError: 업데이트 작업 실패 시
        """
        try:
            # $set 연산자가 없으면 자동으로 추가
            if not any(k.startswith('$') for k in update_data.keys()):
                update_data = {"$set": update_data}
                
            result = self.collection.update_one(
                query, 
                update_data,
                upsert=upsert
            )
            return result.modified_count
        except PyMongoError as e:
            logger.error(f"단일 문서 업데이트 실패: {str(e)}")
            raise OperationError("update_one", self.collection_name, query, e)
    
    def update_many(
        self, 
        query: Dict[str, Any], 
        update_data: Dict[str, Any],
        upsert: bool = False
    ) -> int:
        """여러 문서 업데이트
        
        Args:
            query: 업데이트할 문서 조회 조건
            update_data: 업데이트할 데이터
            upsert: 문서가 없을 경우 삽입 여부
            
        Returns:
            int: 업데이트된 문서 수
            
        Raises:
            OperationError: 업데이트 작업 실패 시
        """
        try:
            # $set 연산자가 없으면 자동으로 추가
            if not any(k.startswith('$') for k in update_data.keys()):
                update_data = {"$set": update_data}
                
            result = self.collection.update_many(
                query, 
                update_data,
                upsert=upsert
            )
            return result.modified_count
        except PyMongoError as e:
            logger.error(f"다중 문서 업데이트 실패: {str(e)}")
            raise OperationError("update_many", self.collection_name, query, e)
    
    def delete_one(self, query: Dict[str, Any]) -> int:
        """단일 문서 삭제
        
        Args:
            query: 삭제할 문서 조회 조건
            
        Returns:
            int: 삭제된 문서 수
            
        Raises:
            OperationError: 삭제 작업 실패 시
        """
        try:
            result = self.collection.delete_one(query)
            return result.deleted_count
        except PyMongoError as e:
            logger.error(f"단일 문서 삭제 실패: {str(e)}")
            raise OperationError("delete_one", self.collection_name, query, e)
    
    def delete_many(self, query: Dict[str, Any]) -> int:
        """여러 문서 삭제
        
        Args:
            query: 삭제할 문서 조회 조건
            
        Returns:
            int: 삭제된 문서 수
            
        Raises:
            OperationError: 삭제 작업 실패 시
        """
        try:
            result = self.collection.delete_many(query)
            return result.deleted_count
        except PyMongoError as e:
            logger.error(f"다중 문서 삭제 실패: {str(e)}")
            raise OperationError("delete_many", self.collection_name, query, e)
    
    def aggregate(self, pipeline: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """집계 파이프라인 실행
        
        Args:
            pipeline: 집계 파이프라인 목록
            
        Returns:
            List[Dict]: 집계 결과
            
        Raises:
            OperationError: 집계 작업 실패 시
        """
        try:
            return list(self.collection.aggregate(pipeline))
        except PyMongoError as e:
            logger.error(f"집계 작업 실패: {str(e)}")
            raise OperationError("aggregate", self.collection_name, pipeline, e)
    
    def close(self) -> None:
        """리소스 정리"""
        # 싱글톤 연결에 대한 참조 포기
        self.db_conn = None
        self.collection = None 