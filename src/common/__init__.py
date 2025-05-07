"""
공통 유틸리티 패키지
"""

import atexit
import logging
from functools import lru_cache

logger = logging.getLogger(__name__)

# 종료 시 리소스 정리를 위한 함수
def _cleanup_mongodb_connections():
    """애플리케이션 종료 시 모든 MongoDB 연결 종료"""
    try:
        from .database.connection import get_database_connection
        
        # lru_cache 사용한 함수의 캐시 정보에 접근
        if hasattr(get_database_connection, 'cache_info'):
            # 캐시된 연결이 있으면 종료
            if hasattr(get_database_connection, 'cache_clear'):
                # 연결 가져오기
                connection = get_database_connection()
                # 명시적으로 연결 종료
                if connection:
                    connection.close()
                # 캐시 정리
                get_database_connection.cache_clear()
                logger.info("MongoDB 연결이 정상적으로 종료되었습니다.")
    except Exception as e:
        logger.error(f"MongoDB 연결 종료 중 오류 발생: {str(e)}")

# 애플리케이션 종료 시 자동으로 실행
atexit.register(_cleanup_mongodb_connections) 