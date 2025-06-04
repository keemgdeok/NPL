"""
분석 관련 서비스 모듈

이 모듈은 통계 및 분석 데이터 처리를 위한 비즈니스 로직을 포함합니다.
라우터는 이 서비스 함수들을 호출하여 요청을 처리합니다.
"""
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta, timezone
from collections import defaultdict

from fastapi import Depends
from motor.motor_asyncio import AsyncIOMotorDatabase

from src.database.repositories.article_repository import (
    SentimentArticleRepository,
    ProcessedArticleRepository
)
# from src.collectors.utils.config import Config # 서비스 계층에서 직접 Config를 사용하는 것은 지양. 필요시 설정값을 주입받도록.
from src.api.core.config import settings # Config 대신 settings 사용 (API_V1_STR 등 이미 사용 중)
from ..core.dependencies import ( # Repository 주입 함수 import
    get_sentiment_article_repository,
    get_processed_article_repository
)

async def get_category_summary_data(
    category: str,
    days: int = 7,
    repo: SentimentArticleRepository = Depends(get_sentiment_article_repository) # Repository 주입
) -> Optional[Dict[str, Any]]:
    """
    특정 카테고리에 대한 통계 요약 데이터를 조회합니다.

    Args:
        category: 조회할 카테고리.
        days: 최근 N일 동안의 데이터를 기준으로 합니다.
        repo: SentimentArticleRepository 인스턴스.

    Returns:
        카테고리 요약 정보 딕셔너리 또는 None.
    """
    start_dt = datetime.now(timezone.utc) - timedelta(days=days)
    start_date_iso = start_dt.isoformat() # MongoDB 쿼리용 ISO 포맷 문자열

    # 감성 분포 집계 (기존 Database.get_category_summary 로직 참고)
    sentiment_distribution = await repo.get_sentiment_distribution(
        category=category,
        days=days
    )

    # 토픽 분포 집계 (기존 Database.get_category_summary 로직 참고)
    match_stage_topic: Dict[str, Any] = {
        "category": category,
        "published_at": {"$gte": start_dt} # ISO 문자열 대신 datetime 객체 직접 사용 (repository에서 처리)
    }
    
    pipeline_topic = [
        {"$match": match_stage_topic},
        {"$unwind": "$topic_analysis.main_topics"}, # topic_analysis 필드와 main_topics 필드가 있다고 가정
        {
            "$group": {
                "_id": "$topic_analysis.main_topics",
                "count": {"$sum": 1},
                # topic_keywords 필드가 있다고 가정하고, 각 토픽 ID별 키워드 목록을 가져옴
                "keywords": {"$first": "$topic_analysis.topic_keywords"} 
            }
        },
        {"$sort": {"count": -1}},
        {"$limit": 5} # 상위 5개 토픽
    ]
    
    topic_distribution_raw = await repo.aggregate(pipeline_topic)
    
    # 토픽 결과 가공 (topic_keywords가 토픽ID를 키로 갖는 딕셔너리라고 가정)
    top_topics_processed = []
    for item in topic_distribution_raw:
        topic_id_str = str(item["_id"]) # _id가 ObjectId일 수 있으므로 문자열로 변환
        # item.get("keywords", {})가 None을 반환할 수 있는 경우 대비
        keywords_data = item.get("keywords")
        keywords_for_topic = keywords_data.get(topic_id_str, []) if isinstance(keywords_data, dict) else []
        top_topics_processed.append({
            "topic_id": topic_id_str,
            "count": item["count"],
            "keywords": keywords_for_topic
        })

    # 전체 기사 수 (해당 카테고리, 기간 내)
    article_count_query: Dict[str, Any] = {
        "category": category,
        "published_at": {"$gte": start_dt} # ISO 문자열 대신 datetime 객체 직접 사용
    }
    article_count = await repo.count_documents(article_count_query)
    
    if article_count == 0 and not sentiment_distribution and not top_topics_processed:
        return None # 데이터가 전혀 없으면 None 반환 또는 빈 요약 반환 고려

    return {
        "category": category,
        "article_count": article_count,
        "sentiment_distribution": sentiment_distribution,
        "top_topics": top_topics_processed,
        "time_range": { # 조회된 데이터의 시간 범위 명시
            "start": start_date_iso,
            "end": datetime.now(timezone.utc).isoformat()
        }
    } 

async def get_stats_summary_data(
    days: int = 7,
    sentiment_repo: SentimentArticleRepository = Depends(get_sentiment_article_repository) # 명시적 이름 사용
) -> Dict[str, Any]:
    """
    전체 통계 요약 데이터를 조회합니다.

    Args:
        days: 최근 N일 동안의 데이터를 기준으로 합니다.
        sentiment_repo: SentimentArticleRepository 인스턴스.

    Returns:
        전체 통계 요약 정보 딕셔너리.
    """
    start_dt = datetime.now(timezone.utc) - timedelta(days=days)
    start_date_iso = start_dt.isoformat()

    # 전체 기사 수
    total_articles_query: Dict[str, Any] = {
        "published_at": {"$gte": start_dt} # ISO 문자열 대신 datetime 객체 직접 사용
    }
    total_articles = await sentiment_repo.count_documents(total_articles_query)
    
    category_keys: List[str] = settings.CATEGORY_KEYS # settings에서 직접 가져오도록 수정

    categories_summary = []
    for category_name in category_keys:
        category_sum = await get_category_summary_data(
            category=category_name, 
            days=days, 
            repo=sentiment_repo # sentiment_repo 전달
        )
        if category_sum:
            categories_summary.append(category_sum)
            
    time_range_data = {
        "start": start_date_iso,
        "end": datetime.now(timezone.utc).isoformat()
    }
    
    return {
        "total_articles": total_articles,
        "categories": categories_summary,
        "time_range": time_range_data
    } 

async def get_article_timeline_data(
    category: Optional[str] = None,
    sentiment: Optional[str] = None, 
    days: int = 30, 
    interval: str = "day",
    repo: SentimentArticleRepository = Depends(get_sentiment_article_repository) # Repository 주입
) -> Dict[str, Any]:
    """시간별 기사 수 타임라인 데이터를 조회합니다.

    Args:
        category: 조회할 카테고리 (선택 사항).
        sentiment: 조회할 감성 (선택 사항).
        days: 최근 N일 동안의 데이터를 기준으로 합니다.
        interval: 시간 간격 ('hour', 'day', 'week').
        repo: SentimentArticleRepository 인스턴스.

    Returns:
        타임라인 데이터 딕셔너리.
    """
    start_dt = datetime.now(timezone.utc) - timedelta(days=days)
    
    match_stage: Dict[str, Any] = {"published_at": {"$gte": start_dt}}
    if category:
        match_stage["category"] = category
    if sentiment:
        match_stage["sentiment_analysis.overall_sentiment.sentiment"] = sentiment
    
    group_format_str = ""
    if interval == "hour":
        group_format_str = "%Y-%m-%d-%H"
    elif interval == "week":
        # MongoDB의 $dateToString은 %V (ISO week)를 직접 지원하지 않을 수 있으므로,
        # $isoWeek를 사용하거나 다른 방식을 고려해야 할 수 있습니다. 여기서는 %G-%V 가정.
        # 또는 $week aggregation operator 사용 고려.
        group_format_str = "%G-%V" 
    else: 
        interval = "day" 
        group_format_str = "%Y-%m-%d"
    
    date_to_string_expr: Dict[str, Any] = {
        "$dateToString": {
            "format": group_format_str, 
            "date": {"$toDate": "$published_at"}, # $toDate를 사용하여 문자열 날짜를 Date 객체로 변환
            "timezone": "UTC" # 명시적 UTC 사용
        }
    }

    pipeline: List[Dict[str, Any]] = [
        {"$match": match_stage},
        {"$group": {"_id": date_to_string_expr, "count": {"$sum": 1}}},
        {"$sort": {"_id": 1}} 
    ]
    
    timeline_raw = await repo.aggregate(pipeline)
    
    # 결과 가공 (날짜를 키, 카운트를 값으로)
    timeline_processed: Dict[str, int] = {item["_id"]: item["count"] for item in timeline_raw if item.get("_id")}

    return {
        "interval": interval,
        "start_date": start_dt.isoformat(),
        "end_date": datetime.now(timezone.utc).isoformat(),
        "timeline": timeline_processed
    }

async def get_sentiment_trends_data(
    category: Optional[str] = None, 
    days: int = 30, 
    interval: str = "day",
    repo: SentimentArticleRepository = Depends(get_sentiment_article_repository) # Repository 주입
) -> Dict[str, Any]:
    """감성 트렌드 타임라인 데이터를 조회합니다."""
    start_dt = datetime.now(timezone.utc) - timedelta(days=days)
    
    match_stage: Dict[str, Any] = {
        "published_at": {"$gte": start_dt},
        # 감성분석 결과가 있는 문서만 대상으로 함
        "sentiment_analysis.overall_sentiment.sentiment": {"$exists": True, "$ne": None} 
    }
    if category:
        match_stage["category"] = category

    group_format_str = ""
    if interval == "hour":
        group_format_str = "%Y-%m-%d-%H"
    elif interval == "week":
        group_format_str = "%G-%V"
    else:
        interval = "day"
        group_format_str = "%Y-%m-%d"

    date_to_string_expr: Dict[str, Any] = {
        "$dateToString": {
            "format": group_format_str, 
            "date": {"$toDate": "$published_at"}, 
            "timezone": "UTC"
        }
    }

    pipeline: List[Dict[str, Any]] = [
        {"$match": match_stage},
        {
            "$group": {
                "_id": {
                    "date": date_to_string_expr,
                    "sentiment": "$sentiment_analysis.overall_sentiment.sentiment"
                },
                "count": {"$sum": 1}
            }
        },
        {
            "$group": {
                "_id": "$_id.date",
                "sentiments": {
                    "$push": {"sentiment": "$_id.sentiment", "count": "$count"}
                }
            }
        },
        {"$sort": {"_id": 1}}
    ]
    
    trends_raw = await repo.aggregate(pipeline)

    # 결과 가공: 각 날짜별로 {sentiment: count} 맵핑
    trends_processed: Dict[str, Dict[str, int]] = defaultdict(dict)
    for item in trends_raw:
        date_str = item.get("_id")
        if date_str:
            for sentiment_data in item.get("sentiments", []):
                trends_processed[date_str][sentiment_data["sentiment"]] = sentiment_data["count"]
    
    return {
        "interval": interval,
        "start_date": start_dt.isoformat(),
        "end_date": datetime.now(timezone.utc).isoformat(),
        "trends": trends_processed
    }

async def get_trending_keywords_data(
    # db: AsyncIOMotorDatabase, # 더 이상 직접 DB 세션 주입받지 않음
    category: Optional[str] = None,
    days: int = 7,
    limit: int = 20,
    processed_repo: ProcessedArticleRepository = Depends(get_processed_article_repository) # Repository 주입
) -> Dict[str, Any]:
    """트렌딩 키워드 데이터를 조회합니다. ProcessedArticle에서 키워드를 집계합니다."""
    start_dt = datetime.now(timezone.utc) - timedelta(days=days)
    
    match_stage: Dict[str, Any] = {
        "processed_at": {"$gte": start_dt}, # processed_article 기준이므로 processed_at 사용
        "keywords": {"$exists": True, "$ne": []} # 키워드가 있는 문서만
    }
    if category:
        match_stage["category"] = category

    pipeline: List[Dict[str, Any]] = [
        {"$match": match_stage},
        {"$unwind": "$keywords"},
        {"$group": {"_id": "$keywords", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
        {"$limit": limit}
    ]
    
    keywords_raw = await processed_repo.aggregate(pipeline)
    
    trending_keywords: List[Dict[str, Any]] = [
        {"keyword": item["_id"], "count": item["count"]}
        for item in keywords_raw if item.get("_id")
    ]
    
    # TODO: 각 키워드별 감성 분포 추가 (선택 사항, 복잡도 증가 가능성)
    # 예시: 각 키워드에 대해 SentimentArticleRepository에서 추가 쿼리
    
    return {
        "time_range": {
            "start": start_dt.isoformat(),
            "end": datetime.now(timezone.utc).isoformat()
        },
        "keywords": trending_keywords
    }

async def get_keyword_network_data(
    # db: AsyncIOMotorDatabase, # Repository 주입으로 변경
    keyword: str,
    depth: int = 1, # 현재는 1단계(직접 연관 키워드)만 지원 가정
    days: int = 7,
    limit_per_node: int = 10, # 각 노드에서 보여줄 연관 키워드 수 제한
    processed_repo: ProcessedArticleRepository = Depends(get_processed_article_repository)
) -> Dict[str, Any]:
    """특정 키워드와 연관된 키워드 네트워크 데이터를 조회합니다."""
    start_dt = datetime.now(timezone.utc) - timedelta(days=days)
    keyword_lower = keyword.lower()

    # 1. 중심 키워드를 포함하는 문서들의 ID 목록 가져오기
    # (processed_repo가 find_ids_by_keyword 같은 메소드를 제공한다고 가정, 없으면 find_many 후 id 추출)
    # 이 예시에서는 find_many로 문서를 가져와서 처리합니다.
    match_center: Dict[str, Any] = {
        "processed_at": {"$gte": start_dt},
        "keywords": keyword_lower
    }
    center_articles = await processed_repo.find_many(
        filter_query=match_center, 
        projection={"keywords": 1}, # keywords 필드만 가져옴
        limit=1000 # 과도한 문서 방지, 적절히 조절 필요
    )

    if not center_articles:
        return {"nodes": [], "links": []} # 중심 키워드 관련 문서 없음

    # 2. 연관 키워드 빈도수 계산
    related_keywords_count: Dict[str, int] = defaultdict(int)
    for article in center_articles:
        if article.get("keywords"):
            for related_kw in article["keywords"]:
                if related_kw != keyword_lower: # 중심 키워드 제외
                    related_keywords_count[related_kw] += 1
    
    # 3. 상위 연관 키워드 선정
    sorted_related_keywords = sorted(
        related_keywords_count.items(), 
        key=lambda item: item[1], 
        reverse=True
    )
    top_related_keywords = [kw for kw, count in sorted_related_keywords[:limit_per_node]]

    # 4. 노드 및 링크 구성
    nodes: List[Dict[str, Any]] = []
    links: List[Dict[str, Any]] = []

    # 중심 노드 추가
    nodes.append({"id": keyword_lower, "group": 1, "size": 20}) # size는 예시, 실제 빈도 등으로 조절 가능

    for i, rel_kw in enumerate(top_related_keywords):
        nodes.append({"id": rel_kw, "group": 2, "size": 10 + related_keywords_count[rel_kw]}) # size 예시
        links.append({"source": keyword_lower, "target": rel_kw, "value": related_keywords_count[rel_kw]})
        
        # depth > 1 경우, 여기서 재귀적으로 연관 키워드의 연관 키워드를 찾을 수 있으나 복잡도 매우 증가
        # 이 예제에서는 depth=1 (직접 연결)만 처리

    return {
        "query_keyword": keyword,
        "time_range": {
            "start": start_dt.isoformat(),
            "end": datetime.now(timezone.utc).isoformat()
        },
        "nodes": nodes,
        "links": links
    } 