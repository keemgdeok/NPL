import requests
from typing import Dict, Any, Optional
from datetime import datetime

class APIClient:
    def __init__(self, base_url: str = "http://localhost:8000/api/v1"):
        self.base_url = base_url.rstrip('/')
    
    def get_articles(
        self,
        category: Optional[str] = None,
        sentiment: Optional[str] = None,
        days: int = 7,
        page: int = 1,
        size: int = 20
    ) -> Dict[str, Any]:
        """기사 목록 조회"""
        params = {
            "days": days,
            "page": page,
            "size": size
        }
        if category:
            params["category"] = category
        if sentiment:
            params["sentiment"] = sentiment
            
        response = requests.get(f"{self.base_url}/articles/", params=params)
        response.raise_for_status()
        return response.json()
    
    def get_article(self, url: str) -> Dict[str, Any]:
        """기사 상세 조회"""
        response = requests.get(f"{self.base_url}/articles/{url}")
        response.raise_for_status()
        return response.json()
    
    def get_categories(self) -> list:
        """카테고리 목록 조회"""
        response = requests.get(f"{self.base_url}/articles/categories")
        response.raise_for_status()
        return response.json()
    
    def get_category_summary(self, category: str, days: int = 7) -> Dict[str, Any]:
        """카테고리별 통계 요약"""
        response = requests.get(
            f"{self.base_url}/analytics/categories/{category}/summary",
            params={"days": days}
        )
        response.raise_for_status()
        return response.json()
    
    def get_stats_summary(self, days: int = 7) -> Dict[str, Any]:
        """전체 통계 요약"""
        response = requests.get(
            f"{self.base_url}/analytics/stats/summary",
            params={"days": days}
        )
        response.raise_for_status()
        return response.json() 