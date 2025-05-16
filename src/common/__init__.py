"""
공통 유틸리티 및 설정 패키지

이 패키지는 프로젝트 전반에서 사용될 수 있는 공통적인 유틸리티 함수,
설정 값 (예: SHARED_CATEGORIES) 등을 포함합니다.
"""

# from .config import SHARED_CATEGORIES # 필요한 경우 공통 설정 import

# # 이전 atexit 기반 MongoDB 연결 정리 코드는 lifespan 관리로 대체되었으므로 제거합니다.
# import atexit
# import logging
# from functools import lru_cache

# logger = logging.getLogger(__name__)

# # 종료 시 리소스 정리를 위한 함수
# def _cleanup_mongodb_connections():
#     """애플리케이션 종료 시 모든 MongoDB 연결 종료"""
#     try:
#         # from .database.connection import get_database_connection # 이제 src.database로 이동됨
#         pass # lifespan에서 관리하므로 여기서는 특별한 작업 없음
#     except Exception as e:
#         # logger.error(f"MongoDB 연결 종료 중 오류 발생: {str(e)}") # 필요시 로깅 유지
#         pass

# # 애플리케이션 종료 시 자동으로 실행
# atexit.register(_cleanup_mongodb_connections)

__all__ = [
    # "SHARED_CATEGORIES", # 필요에 따라 익스포트
] 