from typing import Optional, List, Any, Dict
from pydantic import BaseModel, Field

class ErrorDetail(BaseModel):
    """오류 상세 정보 모델 (주로 유효성 검사 오류에 사용)"""
    loc: Optional[List[str]] = Field(None, title="오류 위치", description="예: [\"body\", \"field_name\"] 또는 [\"query\", \"param_name\"]")
    msg: str = Field(..., title="오류 메시지")
    type: str = Field(..., title="오류 유형", description="예: \"value_error\", \"missing\"")
    ctx: Optional[Dict[str, Any]] = Field(None, title="오류 컨텍스트", description="오류에 대한 추가 컨텍스트 정보")

class ErrorResponse(BaseModel):
    """표준 오류 응답 모델"""
    message: str = Field(..., title="종합 오류 메시지", description="오류에 대한 간략한 설명")
    code: Optional[str] = Field(None, title="오류 코드", description="애플리케이션 정의 오류 코드 (예: \"ITEM_NOT_FOUND\")")
    details: Optional[List[ErrorDetail]] = Field(None, title="상세 오류 정보", description="주로 유효성 검사 오류 시 상세 내역")

    class Config:
        # 예시를 OpenAPI 문서에 포함시키기 위한 설정
        json_schema_extra = {
            "examples": [
                {
                    "message": "Validation Error",
                    "code": "VALIDATION_ERROR",
                    "details": [
                        {
                            "loc": ["body", "email"],
                            "msg": "value is not a valid email address",
                            "type": "value_error.email"
                        }
                    ]
                },
                {
                    "message": "Item not found.",
                    "code": "ITEM_NOT_FOUND",
                },
                {
                    "message": "An unexpected error occurred.",
                    "code": "INTERNAL_SERVER_ERROR",
                }
            ]
        } 