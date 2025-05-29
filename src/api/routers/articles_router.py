from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Query, HTTPException, Depends, Body
from datetime import datetime, timedelta, timezone
from motor.motor_asyncio import AsyncIOMotorDatabase

# from ..database import Database # 변경될 예정
# from ..models import (
#     NewsResponse,
#     NewsArticle,
#     SearchRequest
# ) # 변경될 예정

from ..db.mongodb_handler import Database # 수정된 DB 핸들러 경로
from ..schemas.news_schemas import (
    NewsResponse,
    NewsArticle,
    SearchRequest,
    ArticleResponse # ArticleResponse 추가
)

# get_db_session을 core.dependencies에서 가져옴
from ..core.dependencies import get_db_session, get_db_handler # get_db_handler는 /search 에서 아직 사용
from ..services import article_service # 서비스 모듈 import
from ..core.config import settings # FastAPI 의존성 주입 대신 직접 settings 사용

router = APIRouter()

@router.get("/", response_model=NewsResponse)
async def get_articles(
    category: Optional[str] = None,
    sentiment: Optional[str] = None,
    days: Optional[int] = Query(7, ge=1, le=30),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    db: AsyncIOMotorDatabase = Depends(get_db_session) 
):
    """기사 목록 조회"""
    service_response: Dict[str, Any] = await article_service.get_articles_data(
        db=db,
        category=category,
        sentiment=sentiment,
        days=days if days is not None else 7,
        page=page,
        size=size
    )

    validated_articles = [NewsArticle.model_validate(article) for article in service_response["articles"]]

    return NewsResponse(
        total=service_response["total"],
        page=service_response["page"],
        size=service_response["size"],
        articles=validated_articles
    )

@router.get("/{url:path}", response_model=NewsArticle)
async def get_article_by_url_route(
    url: str,
    db: AsyncIOMotorDatabase = Depends(get_db_session) 
):
    """기사 상세 조회"""
    article_data: Optional[Dict[str, Any]] = await article_service.get_article_by_url_data(db=db, url=url)
    if not article_data:
        raise HTTPException(status_code=404, detail="Article not found")
    
    return NewsArticle.model_validate(article_data)

@router.post("/search", response_model=NewsResponse)
async def search_articles_route(
    search_request: SearchRequest = Body(...),
    db: AsyncIOMotorDatabase = Depends(get_db_session) # 의존성 변경
):
    """고급 검색
    
    다양한 조건으로 기사를 검색합니다.
    """
    # SearchRequest 모델의 필드를 service 함수에 맞게 전달
    service_response: Dict[str, Any] = await article_service.search_articles_data(
        db=db,
        search_query=search_request.query,
        categories=search_request.categories,
        sentiments=search_request.sentiments,
        start_date=search_request.start_date,
        end_date=search_request.end_date,
        press=search_request.press,
        include_keywords=search_request.include_keywords,
        exclude_keywords=search_request.exclude_keywords,
        page=search_request.page if search_request.page is not None else 1, # 스키마에 기본값 있는지 확인
        size=search_request.size if search_request.size is not None else 20  # 스키마에 기본값 있는지 확인
    )
    
    validated_articles = [NewsArticle.model_validate(article) for article in service_response["articles"]]
    
    return NewsResponse(
        total=service_response["total"],
        page=service_response["page"],
        size=service_response["size"],
        articles=validated_articles
    )

@router.get("/categories", response_model=List[str], summary="사용 가능한 뉴스 카테고리 목록 조회")
async def get_categories_list():
    """등록된 모든 뉴스 카테고리의 영문 키 목록을 반환합니다."""
    # from src.collectors.utils.config import Config # 이전 방식
    return settings.CATEGORY_KEYS 