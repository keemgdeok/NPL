from typing import Optional, List
from fastapi import APIRouter, Query, HTTPException, Depends, Body
from datetime import datetime, timedelta

from .database import Database
from .models import (
    NewsResponse,
    NewsArticle,
    CategorySummary,
    StatsSummary,
    TimelineResponse,
    SentimentTrendResponse,
    TrendingKeywordsResponse,
    KeywordNetworkResponse,
    SearchRequest
)

router = APIRouter()

def get_db():
    db = Database()
    try:
        yield db
    finally:
        db.close()

@router.get("/articles", response_model=NewsResponse)
async def get_articles(
    category: Optional[str] = None,
    sentiment: Optional[str] = None,
    days: Optional[int] = Query(7, ge=1, le=30),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    db: Database = Depends(get_db)
):
    """기사 목록 조회"""
    start_date = datetime.now() - timedelta(days=days)
    
    result = db.get_articles(
        category=category,
        sentiment=sentiment,
        start_date=start_date,
        page=page,
        size=size
    )
    
    return NewsResponse(
        total=result["total"],
        page=result["page"],
        size=result["size"],
        articles=[NewsArticle(**article) for article in result["articles"]]
    )

@router.get("/articles/{url:path}", response_model=NewsArticle)
async def get_article(
    url: str,
    db: Database = Depends(get_db)
):
    """기사 상세 조회"""
    article = db.get_article_by_url(url)
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")
    
    return NewsArticle(**article)

@router.get("/categories/{category}/summary", response_model=CategorySummary)
async def get_category_summary(
    category: str,
    days: int = Query(7, ge=1, le=30),
    db: Database = Depends(get_db)
):
    """카테고리별 통계 요약"""
    summary = db.get_category_summary(category, days)
    if not summary:
        raise HTTPException(status_code=404, detail="Category not found")
    
    return CategorySummary(**summary)

@router.get("/stats/summary", response_model=StatsSummary)
async def get_stats_summary(
    days: int = Query(7, ge=1, le=30),
    db: Database = Depends(get_db)
):
    """전체 통계 요약"""
    return StatsSummary(**db.get_stats_summary(days))

@router.get("/categories")
async def get_categories():
    """카테고리 목록"""
    from ..collectors.utils.config import Config
    return list(Config.CATEGORIES.keys())

# 추가: 시간별 기사 수 조회 API
@router.get("/timeline/articles", response_model=TimelineResponse)
async def get_article_timeline(
    category: Optional[str] = None,
    sentiment: Optional[str] = None,
    days: int = Query(30, ge=1, le=90),
    interval: str = Query("day", pattern="^(hour|day|week)$"),
    db: Database = Depends(get_db)
):
    """시간별 기사 수 조회
    
    hour, day, week 단위로 시간별 기사 수를 제공합니다.
    """
    return db.get_article_timeline(category, sentiment, days, interval)

# 추가: 감성 트렌드 조회 API
@router.get("/sentiment/trends", response_model=SentimentTrendResponse)
async def get_sentiment_trends(
    category: Optional[str] = None,
    days: int = Query(30, ge=1, le=90),
    interval: str = Query("day", pattern="^(hour|day|week)$"),
    db: Database = Depends(get_db)
):
    """감성 트렌드 조회
    
    시간별 감성 분포 추이를 제공합니다.
    """
    return db.get_sentiment_trends(category, days, interval)

# 추가: 트렌딩 키워드 조회 API
@router.get("/keywords/trending", response_model=TrendingKeywordsResponse)
async def get_trending_keywords(
    category: Optional[str] = None,
    days: int = Query(7, ge=1, le=30),
    limit: int = Query(20, ge=5, le=50),
    db: Database = Depends(get_db)
):
    """트렌딩 키워드 조회
    
    기간 내 중요도 높은 키워드를 반환합니다.
    """
    return db.get_trending_keywords(category, days, limit)

# 추가: 키워드 네트워크 조회 API
@router.get("/keywords/network", response_model=KeywordNetworkResponse)
async def get_keyword_network(
    keyword: str,
    depth: int = Query(1, ge=1, le=3),
    days: int = Query(7, ge=1, le=30),
    db: Database = Depends(get_db)
):
    """키워드 네트워크 조회
    
    특정 키워드를 중심으로 한 연관 키워드 네트워크를 제공합니다.
    """
    return db.get_keyword_network(keyword, depth, days)

# 추가: 고급 검색 API
@router.post("/search", response_model=NewsResponse)
async def search_articles(
    search_request: SearchRequest = Body(...),
    db: Database = Depends(get_db)
):
    """고급 검색
    
    다양한 조건으로 기사를 검색합니다.
    """
    result = db.search_articles(search_request.dict())
    
    return NewsResponse(
        total=result["total"],
        page=result["page"],
        size=result["size"],
        articles=[NewsArticle(**article) for article in result["articles"]]
    ) 