from typing import Optional
from fastapi import APIRouter, Query, HTTPException, Depends
from datetime import datetime, timedelta

from .database import Database
from .models import (
    NewsResponse,
    NewsArticle,
    CategorySummary,
    StatsSummary
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
    from ..collectors.utils.config import NaverNewsConfig
    return list(NaverNewsConfig.CATEGORIES.keys()) 