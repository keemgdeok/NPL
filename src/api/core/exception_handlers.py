import logging
from typing import Union

from fastapi import Request, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError, HTTPException as FastAPIHTTPException
from starlette.exceptions import HTTPException as StarletteHTTPException

from src.api.schemas.error_schema import ErrorResponse, ErrorDetail
from src.database.exceptions import NotFoundError, OperationError, DatabaseError

# 로거 설정
logger = logging.getLogger(__name__)
# 기본 로깅 레벨 설정 (실제 환경에서는 main.py 등에서 전역적으로 설정하는 것이 좋음)
# logging.basicConfig(level=logging.INFO)

async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """FastAPI의 RequestValidationError를 처리하여 표준 형식의 422 응답을 반환합니다."""
    details = []
    for error in exc.errors():
        details.append(
            ErrorDetail(
                loc=list(error.get("loc", [])) or None, # loc이 빈 튜플일 경우 None으로 처리
                msg=error.get("msg", ""),
                type=error.get("type", ""),
                ctx=error.get("ctx")
            )
        )
    logger.warning(f"Validation error for request {request.method} {request.url.path}: {details}", extra={"details": details})
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=ErrorResponse(
            message="Validation Error", 
            code="VALIDATION_ERROR", 
            details=details
        ).model_dump(exclude_none=True)
    )

async def http_exception_handler(request: Request, exc: Union[FastAPIHTTPException, StarletteHTTPException]) -> JSONResponse:
    """FastAPI 및 Starlette의 HTTPException을 처리하여 표준 형식의 응답을 반환합니다."""
    error_code = getattr(exc, "error_code", "HTTP_EXCEPTION") # 커스텀 error_code가 있다면 사용
    logger.warning(
        f"HTTP exception for request {request.method} {request.url.path}: {exc.status_code} - {exc.detail}", 
        extra={"status_code": exc.status_code, "detail": exc.detail, "error_code": error_code}
    )
    return JSONResponse(
        status_code=exc.status_code,
        content=ErrorResponse(
            message=str(exc.detail),
            code=error_code
        ).model_dump(exclude_none=True),
        headers=getattr(exc, "headers", None)
    )

async def not_found_error_handler(request: Request, exc: NotFoundError) -> JSONResponse:
    """src.common.database.exceptions.NotFoundError를 처리하여 404 응답을 반환합니다."""
    logger.warning(f"Resource not found for request {request.method} {request.url.path}: {exc}", extra={"error_message": str(exc)})
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content=ErrorResponse(message=str(exc), code="NOT_FOUND").model_dump(exclude_none=True)
    )

async def operation_error_handler(request: Request, exc: OperationError) -> JSONResponse:
    """src.common.database.exceptions.OperationError를 처리하여 400 또는 500 응답을 반환합니다."""
    # OperationError의 종류에 따라 status_code를 다르게 설정할 수 있습니다.
    # 여기서는 일단 400으로 통일합니다.
    status_code = status.HTTP_400_BAD_REQUEST 
    error_code = "OPERATION_ERROR"
    logger.error(
        f"Operation error for request {request.method} {request.url.path}: {exc}", 
        exc_info=True, 
        extra={"error_message": str(exc), "error_code": error_code}
    )
    return JSONResponse(
        status_code=status_code,
        content=ErrorResponse(message=str(exc), code=error_code).model_dump(exclude_none=True)
    )

async def database_error_handler(request: Request, exc: DatabaseError) -> JSONResponse:
    """src.common.database.exceptions.DatabaseError를 처리하여 500 응답을 반환합니다."""
    logger.error(
        f"Database error for request {request.method} {request.url.path}: {exc}", 
        exc_info=True, 
        extra={"error_message": str(exc)}
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=ErrorResponse(message="A database error occurred.", code="DATABASE_ERROR").model_dump(exclude_none=True)
    )

async def general_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """처리되지 않은 모든 Exception을 잡아 500 응답을 반환합니다."""
    logger.error(
        f"Unhandled exception for request {request.method} {request.url.path}: {exc}", 
        exc_info=True, # 스택 트레이스 로깅
        extra={"error_message": str(exc)}
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=ErrorResponse(message="An unexpected internal server error occurred.", code="INTERNAL_SERVER_ERROR").model_dump(exclude_none=True)
    ) 