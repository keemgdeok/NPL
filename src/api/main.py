import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
# from .routers import router # 기존 단일 라우터 import 제거

# 새로 분리된 라우터 모듈 임포트
from .routers import articles_router, analytics_router
from .core.config import settings # API_V1_STR 사용을 위해 import
# src.database.connection 모듈에서 필요한 함수들을 import 합니다.
from src.database.connection import (
    connect_to_mongo, 
    close_mongo_connection, 
    create_indexes_on_startup,
    get_database # lifespan에서 DB 가져오기 위함
)
from src.database.exceptions import NotFoundError, OperationError, DatabaseError
from src.api.core.exception_handlers import (
    validation_exception_handler,
    http_exception_handler,
    not_found_error_handler,
    operation_error_handler,
    database_error_handler,
    general_exception_handler
)
# from src.common.database.exceptions import NotFoundError, OperationError, DatabaseError # 이전 경로 주석 처리 또는 삭제

# --- 로깅 설정 --- #
# 기본 로깅 레벨 및 포맷 설정
log_level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)
logging.basicConfig(
    level=log_level,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)
# --- 로깅 설정 끝 --- #

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting up News Pipeline API...")
    logger.info(f"Database URL: {settings.DATABASE_URL}, DB Name: {settings.MONGO_DATABASE_NAME}")
    
    # MongoDB 연결 시도 및 재시도 로직 포함
    await connect_to_mongo(
        db_url=settings.DATABASE_URL, 
        db_name=settings.MONGO_DATABASE_NAME, 
        max_retries=settings.MONGO_MAX_RETRIES, 
        retry_delay=settings.MONGO_RETRY_DELAY
    )
    
    # 연결 성공 후 DB 가져오기
    db = await get_database() # connect_to_mongo 이후 호출 보장
    if db:
        logger.info("Successfully connected to MongoDB.")
        # 시작 시 인덱스 생성
        await create_indexes_on_startup(db) # db 객체 전달
        logger.info("Database indexes checked/created.")
    else:
        logger.error("Failed to get database instance after connection attempt.")
        # 여기서 애플리케이션을 중단하거나, 재시도 로직을 추가할 수 있습니다.
        # 현재는 에러 로그만 남기고 진행합니다.
    
    yield
    
    logger.info("Shutting down News Pipeline API...")
    await close_mongo_connection()
    logger.info("MongoDB connection closed.")

app = FastAPI(
    title=settings.PROJECT_NAME, # config.py의 설정값 사용
    description="News Pipeline API - Provides access to news articles and analytics.",
    version="1.0.0", # 버전도 config에서 관리 가능
    lifespan=lifespan, # lifespan 컨텍스트 매니저 등록
    openapi_url=f"{settings.API_V1_STR}/openapi.json"
)

# CORS 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 실제 운영 환경에서는 구체적인 도메인 지정 필요
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 라우터 등록
# app.include_router(router, prefix="/api/v1") # 기존 단일 라우터 등록 제거

# API_V1_STR을 사용하여 일관된 prefix 관리
api_v1_prefix = settings.API_V1_STR

app.include_router(
    articles_router.router, 
    prefix=f"{api_v1_prefix}/articles", 
    tags=["Articles & Search"]
)
app.include_router(
    analytics_router.router, 
    prefix=f"{api_v1_prefix}/analytics", 
    tags=["Analytics & Stats"]
)

@app.get(f"{api_v1_prefix}") # API 루트 경로도 버전 prefix 적용
async def api_root():
    return {"message": f"Welcome to the {settings.PROJECT_NAME} - Version 1"}

@app.get("/")
async def root():
    return {"message": "Welcome to the News Pipeline API (Root)"}

# --- 전역 예외 핸들러 등록 --- #
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(StarletteHTTPException, http_exception_handler) # FastAPI의 HTTPException도 StarletteHTTPException을 상속
app.add_exception_handler(NotFoundError, not_found_error_handler)
app.add_exception_handler(OperationError, operation_error_handler)
app.add_exception_handler(DatabaseError, database_error_handler)
app.add_exception_handler(Exception, general_exception_handler) # 가장 마지막에 등록하여 모든 예외 처리
# --- 전역 예외 핸들러 등록 끝 --- #

@app.get("/health", tags=["Health Check"], summary="API 상태 확인")
async def health_check():
    """API 서버의 현재 상태를 반환합니다."""
    return {"status": "ok", "message": "News Pipeline API is running!"}

# 기본 로깅 설정이 여기서 한번 더 호출될 필요는 없습니다.
# 이미 상단에서 logging.basicConfig로 전역 설정되었습니다.
# if __name__ == "__main__":
#     import uvicorn
#     # LOG_LEVEL 환경 변수를 uvicorn 로그 레벨로 변환
#     uvicorn_log_level = settings.LOG_LEVEL.lower()
#     if uvicorn_log_level == "trace": # uvicorn은 trace 지원 안함
#        uvicorn_log_level = "debug" 

#     logger.info(f"Starting Uvicorn server with log level: {uvicorn_log_level}")
#     uvicorn.run(app, host="0.0.0.0", port=8000, log_level=uvicorn_log_level) 