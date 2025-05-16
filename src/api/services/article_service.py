"""
기사 관련 서비스 모듈

이 모듈은 기사 데이터 처리를 위한 비즈니스 로직을 포함합니다.
라우터는 이 서비스 함수들을 호출하여 요청을 처리합니다.
"""
from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime, timedelta
import re
from datetime import timezone

from fastapi import Depends
from motor.motor_asyncio import AsyncIOMotorDatabase

from src.database.repositories.article_repository import SentimentArticleRepository
from src.api.schemas.news_schemas import ArticleResponse, SearchRequest # SearchRequest 추가
from ..core.dependencies import (
    get_sentiment_article_repository # SentimentArticleRepository 주입 함수 추가
)

# 페이지네이션 응답을 위한 Pydantic 모델을 정의할 수도 있습니다.
# from pydantic import BaseModel
# class PaginatedArticleResponse(BaseModel):
#     total: int
#     page: int
#     size: int
#     items: List[ArticleResponse] # 또는 List[Dict[str, Any]]

async def get_articles_data(
    category: Optional[str] = None,
    sentiment: Optional[str] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    page: int = 1,
    size: int = 20,
    repo: SentimentArticleRepository = Depends(get_sentiment_article_repository),
) -> Dict[str, Any]:
    """
    필터 조건에 따라 기사 목록 및 페이지네이션 정보를 조회합니다.

    Args:
        category: 필터링할 카테고리.
        sentiment: 필터링할 감성.
        start_date: 조회 시작 날짜.
        end_date: 조회 종료 날짜.
        page: 현재 페이지 번호.
        size: 페이지 당 기사 수.
        repo: SentimentArticleRepository 인스턴스.

    Returns:
        기사 목록과 페이지네이션 정보를 포함하는 딕셔너리.
    """
    query: Dict[str, Any] = {}
    if category:
        query["category"] = category
    if sentiment:
        query["sentiment_analysis.overall_sentiment.sentiment"] = sentiment

    date_query: Dict[str, Any] = {}
    if start_date:
        if start_date.tzinfo is None:
            start_date = start_date.replace(tzinfo=timezone.utc)
        date_query["$gte"] = start_date.isoformat()
    if end_date:
        if end_date.tzinfo is None:
            end_date = end_date.replace(tzinfo=timezone.utc)
        date_query["$lte"] = end_date.isoformat()
    if date_query:
        query["published_at"] = date_query
    
    total = await repo.count_documents(query)
    
    articles = await repo.find_many(
        filter_query=query,
        sort_key="published_at", 
        sort_order=-1,
        skip=(page - 1) * size,
        limit=size
    )
    
    return {
        "total": total,
        "page": page,
        "size": size,
        "articles": articles
    }

async def search_articles_data(
    search_request: SearchRequest,
    repo: SentimentArticleRepository = Depends(get_sentiment_article_repository),
    page: int = 1,
    size: int = 20,
) -> Dict[str, Any]:
    """
    고급 검색 조건에 따라 기사 목록 및 페이지네이션 정보를 조회합니다.

    Args:
        search_request: 검색 조건을 담은 SearchRequest 모델 객체.
        repo: SentimentArticleRepository 인스턴스.
        page: 현재 페이지 번호.
        size: 페이지 당 기사 수.

    Returns:
        검색된 기사 목록과 페이지네이션 정보를 포함하는 딕셔너리.
    """
    query: Dict[str, Any] = {}
    query_parts: List[Dict[str, Any]] = []

    if search_request.query:
        search_query_terms = []
        keywords_for_search = re.split(r'\s+', search_request.query.lower())
        
        title_queries = []
        for kw in keywords_for_search:
            if len(kw) >= 1:
                title_queries.append({"title": {"$regex": kw, "$options": "i"}})
        if title_queries:
            search_query_terms.append({"$or": title_queries})

        keyword_part_for_or = {"keywords": {"$in": keywords_for_search}}
        
        if search_query_terms and keyword_part_for_or:
             query_parts.append({"$or": [search_query_terms[0], keyword_part_for_or]})
        elif search_query_terms:
            query_parts.append(search_query_terms[0])
        elif keyword_part_for_or:
            query_parts.append(keyword_part_for_or)

    if search_request.categories:
        query_parts.append({"category": {"$in": search_request.categories}})

    if search_request.sentiments:
        query_parts.append({"sentiment_analysis.overall_sentiment.sentiment": {"$in": search_request.sentiments}})

    date_filter_conditions: Dict[str, Any] = {}
    if search_request.start_date:
        s_date = search_request.start_date
        if s_date.tzinfo is None:
            s_date = s_date.replace(tzinfo=timezone.utc)
        date_filter_conditions["$gte"] = s_date
    if search_request.end_date:
        e_date = search_request.end_date
        if e_date.tzinfo is None:
            e_date = e_date.replace(tzinfo=timezone.utc)
        date_filter_conditions["$lte"] = e_date
    if date_filter_conditions:
        query_parts.append({"published_at": date_filter_conditions})
    
    if search_request.press:
        query_parts.append({"press": {"$in": search_request.press}})

    if search_request.include_keywords:
        query_parts.append({"keywords": {"$all": [kw.lower() for kw in search_request.include_keywords]}})
    if search_request.exclude_keywords:
        query_parts.append({"keywords": {"$nin": [kw.lower() for kw in search_request.exclude_keywords]}})
    
    if query_parts:
        query["$and"] = query_parts
    else:
        query = {} 

    total = await repo.count_documents(query)
    articles = await repo.find_many(
        filter_query=query,
        sort_key="published_at", 
        sort_order=-1, 
        skip=(page - 1) * size, 
        limit=size
    )

    return {
        "total": total,
        "page": page,
        "size": size,
        "articles": articles
    }

async def get_article_by_url_data(
    url: str,
    repo: SentimentArticleRepository = Depends(get_sentiment_article_repository),
) -> Optional[Dict[str, Any]]:
    """
    주어진 URL에 해당하는 단일 기사 정보를 조회합니다.

    Args:
        url: 조회할 기사의 전체 URL.
        repo: SentimentArticleRepository 인스턴스.

    Returns:
        기사 정보 딕셔너리 또는 None.
    """
    article = await repo.get_article_by_url(url)
    return article 