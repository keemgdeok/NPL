"""
MongoDB 데이터베이스 작업 관련 예외 정의
"""

from typing import Optional, Any


class DatabaseError(Exception):
    """데이터베이스 작업 관련 기본 예외 클래스"""
    
    def __init__(self, message: str, original_error: Optional[Exception] = None):
        self.message = message
        self.original_error = original_error
        super().__init__(message)


class MongoDBConnectionError(DatabaseError):
    """데이터베이스 연결 관련 예외"""
    
    def __init__(self, 
                message: str = "MongoDB 연결 실패", 
                original_error: Optional[Exception] = None):
        super().__init__(message, original_error)


class OperationError(DatabaseError):
    """데이터베이스 작업 실행 관련 예외"""
    
    def __init__(self, 
                operation: str, 
                collection: str,
                query: Optional[Any] = None,
                original_error: Optional[Exception] = None):
        message = f"MongoDB {operation} 작업 실패 (컬렉션: {collection})"
        if query:
            message += f", 쿼리: {query}"
        super().__init__(message, original_error) 