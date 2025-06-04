from typing import Optional, List
from fastapi import APIRouter, Query, HTTPException, Depends
from datetime import datetime, timedelta
from motor.motor_asyncio import AsyncIOMotorDatabase

from ..db.mongodb_handler import Database # Database 클래스 자체는 여전히 필요할 수 있음 (타입 힌팅 등)
from ..schemas.news_schemas import (
    CategorySummary,
    StatsSummary,
    TimelineResponse,
    SentimentTrendResponse,
    TrendingKeywordsResponse,
    KeywordNetworkResponse
)

# get_db_session 및 get_db_handler(다른 라우트에서 아직 사용)를 core.dependencies에서 가져옴
from ..core.dependencies import get_db_session, get_db_handler
from ..services import analytics_service # 서비스 모듈 import

router = APIRouter()

@router.get("/categories/{category}/summary", response_model=CategorySummary)
async def get_category_summary_route(
    category: str,
    days: int = Query(7, ge=1, le=30),
    db: AsyncIOMotorDatabase = Depends(get_db_session) # 의존성 변경
):
    """카테고리별 통계 요약"""
    summary_data = await analytics_service.get_category_summary_data(
        db=db, 
        category=category, 
        days=days
    )
    if not summary_data:
        raise HTTPException(status_code=404, detail=f"Summary for category '{category}' not found or no data available")
    
    return CategorySummary.model_validate(summary_data)

@router.get("/stats/summary", response_model=StatsSummary)
async def get_stats_summary_route(
    days: int = Query(7, ge=1, le=30),
    db: AsyncIOMotorDatabase = Depends(get_db_session) # 의존성 변경
):
    """전체 통계 요약"""
    summary_data = await analytics_service.get_stats_summary_data(db=db, days=days)
    # 서비스 함수가 이미 Dict를 반환하므로, StatsSummary.model_validate로 변환
    return StatsSummary.model_validate(summary_data)

@router.get("/timeline/articles", response_model=TimelineResponse)
async def get_article_timeline_route(
    category: Optional[str] = None,
    sentiment: Optional[str] = None,
    days: int = Query(30, ge=1, le=90),
    interval: str = Query("day", pattern="^(hour|day|week)$"),
    db: AsyncIOMotorDatabase = Depends(get_db_session) # 의존성 변경
):
    """시간별 기사 수 조회
    
    hour, day, week 단위로 시간별 기사 수를 제공합니다.
    """
    timeline_data = await analytics_service.get_article_timeline_data(
        db=db,
        category=category, 
        sentiment=sentiment, 
        days=days, 
        interval=interval
    )
    return TimelineResponse.model_validate(timeline_data)

@router.get("/sentiment/trends", response_model=SentimentTrendResponse)
async def get_sentiment_trends_route(
    category: Optional[str] = None,
    days: int = Query(30, ge=1, le=90),
    interval: str = Query("day", pattern="^(hour|day|week)$"),
    db: AsyncIOMotorDatabase = Depends(get_db_session) # 의존성 변경
):
    """감성 트렌드 조회
    
    시간별 감성 분포 추이를 제공합니다.
    """
    trend_data = await analytics_service.get_sentiment_trends_data(
        db=db,
        category=category, 
        days=days, 
        interval=interval
    )
    return SentimentTrendResponse.model_validate(trend_data)

@router.get("/keywords/trending", response_model=TrendingKeywordsResponse)
async def get_trending_keywords_route(
    category: Optional[str] = None,
    days: int = Query(7, ge=1, le=30),
    limit: int = Query(20, ge=5, le=50),
    db: AsyncIOMotorDatabase = Depends(get_db_session) # 의존성 변경
):
    """트렌딩 키워드 조회
    
    기간 내 중요도 높은 키워드를 반환합니다.
    """
    keywords_data = await analytics_service.get_trending_keywords_data(
        db=db,
        category=category, 
        days=days, 
        limit=limit
    )
    return TrendingKeywordsResponse.model_validate(keywords_data)

@router.get("/keywords/network", response_model=KeywordNetworkResponse)
async def get_keyword_network_route(
    keyword: str,
    depth: int = Query(1, ge=1, le=3),
    days: int = Query(7, ge=1, le=30),
    db: AsyncIOMotorDatabase = Depends(get_db_session) # 의존성 변경
):
    """키워드 네트워크 조회
    
    특정 키워드를 중심으로 한 연관 키워드 네트워크를 제공합니다.
    """
    network_data = await analytics_service.get_keyword_network_data(
        db=db,
        keyword=keyword,
        depth=depth,
        days=days
    )
    return KeywordNetworkResponse.model_validate(network_data) 