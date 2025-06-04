"""
MongoDB 데이터 액세스 Repository 패턴 구현 (비동기 지원)

이 모듈은 MongoDB 컬렉션에 대한 비동기 CRUD 작업을 추상화하는 Repository 클래스를 제공합니다.
"""

from typing import Dict, List, Any, Optional, Generic, TypeVar, Union, Tuple
import logging

# from pymongo.collection import Collection
# from pymongo.errors import PyMongoError
from motor.motor_asyncio import AsyncIOMotorCollection, AsyncIOMotorDatabase # Motor Collection 사용
from pymongo.errors import PyMongoError # 에러는 그대로 사용 가능
from bson import ObjectId # ObjectId는 그대로 사용

# from .connection import get_database_connection
from .connection import get_database # 수정된 connection 모듈의 함수
from .collections import CollectionName, get_collection_info # get_collection_indexes는 제거될 수 있음
from .exceptions import OperationError

logger = logging.getLogger(__name__)

T = TypeVar('T')

class BaseRepository(Generic[T]):
    """MongoDB 기본 저장소 클래스 (비동기 지원)
    
    일반적인 비동기 CRUD 작업을 제공합니다.
    """
    
    def __init__(self, db_session: AsyncIOMotorDatabase, collection_name: Union[str, CollectionName]):
        if isinstance(collection_name, CollectionName):
            self.collection_name = collection_name.value
        else:
            self.collection_name = collection_name
            
        # 비동기 데이터베이스 객체 및 컬렉션 할당
        self.db_session = db_session
        self.collection: AsyncIOMotorCollection = self.db_session[self.collection_name]
        
        # # 인덱스 생성 로직은 connection.py의 create_indexes_on_startup으로 이전됨
        # if create_indexes:
        #     # ... (이전 로직 주석 처리 또는 삭제)

    async def find_one(
        self, 
        query: Dict[str, Any],
        projection: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict[str, Any]]:
        try:
            return await self.collection.find_one(query, projection)
        except PyMongoError as e:
            logger.error(f"비동기 단일 문서 조회 실패: {str(e)}")
            raise OperationError("find_one (async)", self.collection_name, query, e)

    async def find_many(
        self, 
        query: Dict[str, Any] = None, 
        projection: Optional[Dict[str, Any]] = None,
        sort_key: Optional[Union[str, List[Tuple[str, int]]]] = None,
        sort_order: int = -1, # pymongo와 동일하게 사용 가능
        skip: int = 0, 
        limit: int = 0
    ) -> List[Dict[str, Any]]:
        try:
            query = query or {}
            cursor = self.collection.find(query, projection)
            
            if sort_key:
                if isinstance(sort_key, str):
                    cursor = cursor.sort(sort_key, sort_order)
                else:
                    cursor = cursor.sort(sort_key) # motor도 튜플 리스트 정렬 지원
            
            if skip > 0: # skip이 0일 경우 적용 안 함
                cursor = cursor.skip(skip)
            
            if limit > 0: # limit이 0일 경우 전체 결과
                cursor = cursor.limit(limit)
                
            return await cursor.to_list(length=limit if limit > 0 else None) # length=None이면 전체
        except PyMongoError as e:
            logger.error(f"비동기 다중 문서 조회 실패: {str(e)}")
            raise OperationError("find_many (async)", self.collection_name, query, e)

    async def count(self, query: Dict[str, Any] = None) -> int:
        try:
            query = query or {}
            # motor는 count_documents에 filter 인자만 받음 (estimate_document_count도 고려)
            return await self.collection.count_documents(query)
        except PyMongoError as e:
            logger.error(f"비동기 문서 개수 조회 실패: {str(e)}")
            raise OperationError("count (async)", self.collection_name, query, e)

    async def insert_one(self, document: Dict[str, Any]) -> str:
        try:
            result = await self.collection.insert_one(document)
            return str(result.inserted_id)
        except PyMongoError as e:
            logger.error(f"비동기 단일 문서 삽입 실패: {str(e)}")
            raise OperationError("insert_one (async)", self.collection_name, None, e)

    async def insert_many(self, documents: List[Dict[str, Any]]) -> List[str]:
        try:
            result = await self.collection.insert_many(documents)
            return [str(id) for id in result.inserted_ids]
        except PyMongoError as e:
            logger.error(f"비동기 다중 문서 삽입 실패: {str(e)}")
            raise OperationError("insert_many (async)", self.collection_name, None, e)

    async def update_one(
        self, 
        query: Dict[str, Any], 
        update_data: Dict[str, Any],
        upsert: bool = False
    ) -> int:
        try:
            if not any(k.startswith('$') for k in update_data.keys()):
                update_data = {"$set": update_data}
            result = await self.collection.update_one(query, update_data, upsert=upsert)
            return result.modified_count
        except PyMongoError as e:
            logger.error(f"비동기 단일 문서 업데이트 실패: {str(e)}")
            raise OperationError("update_one (async)", self.collection_name, query, e)

    async def update_many(
        self, 
        query: Dict[str, Any], 
        update_data: Dict[str, Any],
        upsert: bool = False # motor의 update_many는 upsert를 지원하지 않음, 필요시 별도 로직 또는 반복 update_one
    ) -> int:
        # 참고: motor의 update_many는 upsert 옵션을 직접 지원하지 않습니다.
        # upsert=True일 경우, find 후 update_one을 반복하거나, bulk_write를 사용하는 등의 전략이 필요할 수 있습니다.
        # 여기서는 upsert=False인 경우만 간단히 처리합니다.
        if upsert:
            logger.warning("motor의 update_many는 upsert를 직접 지원하지 않습니다. upsert=True는 무시됩니다.")
        try:
            if not any(k.startswith('$') for k in update_data.keys()):
                update_data = {"$set": update_data}
            result = await self.collection.update_many(query, update_data)
            return result.modified_count
        except PyMongoError as e:
            logger.error(f"비동기 다중 문서 업데이트 실패: {str(e)}")
            raise OperationError("update_many (async)", self.collection_name, query, e)

    async def delete_one(self, query: Dict[str, Any]) -> int:
        try:
            result = await self.collection.delete_one(query)
            return result.deleted_count
        except PyMongoError as e:
            logger.error(f"비동기 단일 문서 삭제 실패: {str(e)}")
            raise OperationError("delete_one (async)", self.collection_name, query, e)

    async def delete_many(self, query: Dict[str, Any]) -> int:
        try:
            result = await self.collection.delete_many(query)
            return result.deleted_count
        except PyMongoError as e:
            logger.error(f"비동기 다중 문서 삭제 실패: {str(e)}")
            raise OperationError("delete_many (async)", self.collection_name, query, e)

    async def aggregate(self, pipeline: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        try:
            cursor = self.collection.aggregate(pipeline)
            return await cursor.to_list(length=None)
        except PyMongoError as e:
            logger.error(f"비동기 집계 작업 실패: {str(e)}")
            # pipeline은 dict가 아닐 수 있으므로 query 대신 None 전달
            raise OperationError("aggregate (async)", self.collection_name, None, e)

    # def close(self) -> None: # 클라이언트 연결은 중앙에서 관리하므로 Repository 레벨의 close는 불필요
    #     pass 