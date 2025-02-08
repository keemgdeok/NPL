from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from pymongo import MongoClient, DESCENDING
from bson import ObjectId

from ..collectors.utils.config import NaverNewsConfig

class Database:
    def __init__(self):
        self.client = MongoClient(NaverNewsConfig.MONGODB_URI)
        self.db = self.client[NaverNewsConfig.DATABASE_NAME]
    
    def get_articles(
        self,
        category: Optional[str] = None,
        sentiment: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        page: int = 1,
        size: int = 20
    ) -> Dict[str, Any]:
        """기사 목록 조회"""
        # 쿼리 조건 구성
        query = {}
        if category:
            query["category"] = category
        if sentiment:
            query["sentiment_analysis.overall_sentiment.sentiment"] = sentiment
        if start_date or end_date:
            date_query = {}
            if start_date:
                date_query["$gte"] = start_date.isoformat()
            if end_date:
                date_query["$lte"] = end_date.isoformat()
            if date_query:
                query["published_at"] = date_query
        
        # 전체 개수 조회
        total = self.db.sentiment_articles.count_documents(query)
        
        # 페이지네이션 적용하여 데이터 조회
        articles = list(self.db.sentiment_articles
                      .find(query)
                      .sort("published_at", DESCENDING)
                      .skip((page - 1) * size)
                      .limit(size))
        
        return {
            "total": total,
            "page": page,
            "size": size,
            "articles": articles
        }
    
    def get_article_by_url(self, url: str) -> Optional[Dict[str, Any]]:
        """URL로 기사 상세 조회"""
        return self.db.sentiment_articles.find_one({"url": url})
    
    def get_category_summary(
        self,
        category: str,
        days: int = 7
    ) -> Optional[Dict[str, Any]]:
        """카테고리별 통계 요약"""
        start_date = datetime.now() - timedelta(days=days)
        
        # 기본 쿼리 조건
        match_stage = {
            "$match": {
                "category": category,
                "published_at": {"$gte": start_date.isoformat()}
            }
        }
        
        # 감정 분포 집계
        sentiment_distribution = self.db.sentiment_articles.aggregate([
            match_stage,
            {
                "$group": {
                    "_id": "$sentiment_analysis.overall_sentiment.sentiment",
                    "count": {"$sum": 1}
                }
            }
        ])
        
        # 토픽 분포 집계
        topic_distribution = self.db.sentiment_articles.aggregate([
            match_stage,
            {"$unwind": "$topic_analysis.main_topics"},
            {
                "$group": {
                    "_id": "$topic_analysis.main_topics",
                    "count": {"$sum": 1},
                    "keywords": {"$first": "$topic_analysis.topic_keywords"}
                }
            },
            {"$sort": {"count": -1}},
            {"$limit": 5}
        ])
        
        # 전체 기사 수
        article_count = self.db.sentiment_articles.count_documents({
            "category": category,
            "published_at": {"$gte": start_date.isoformat()}
        })
        
        return {
            "category": category,
            "article_count": article_count,
            "sentiment_distribution": {item["_id"]: item["count"] for item in sentiment_distribution},
            "top_topics": [
                {
                    "topic_id": item["_id"],
                    "count": item["count"],
                    "keywords": item["keywords"][item["_id"]]
                }
                for item in topic_distribution
            ]
        }
    
    def get_stats_summary(self, days: int = 7) -> Dict[str, Any]:
        """전체 통계 요약"""
        start_date = datetime.now() - timedelta(days=days)
        
        # 전체 기사 수
        total_articles = self.db.sentiment_articles.count_documents({
            "published_at": {"$gte": start_date.isoformat()}
        })
        
        # 카테고리별 요약
        categories = []
        for category in NaverNewsConfig.CATEGORIES.keys():
            summary = self.get_category_summary(category, days)
            if summary:
                categories.append(summary)
        
        # 시간 범위
        time_range = {
            "start": start_date,
            "end": datetime.now()
        }
        
        return {
            "total_articles": total_articles,
            "categories": categories,
            "time_range": time_range
        }
    
    def close(self):
        """데이터베이스 연결 종료"""
        self.client.close() 