import requests
import os
import streamlit as st
from typing import Dict, Any, Optional, List, Union
from datetime import datetime, timedelta
import json
import time

class APIError(Exception):
    """API 요청 중 발생한 오류를 나타내는 예외 클래스"""
    pass

class APIClient:
    """API 클라이언트 클래스
    
    뉴스 분석 API와의 통신을 담당하는 중앙화된 클라이언트 클래스입니다.
    모든 API 호출은 이 클래스를 통해 이루어지며, API 응답 데이터의 일관성을 보장합니다.
    """
    
    def __init__(self, base_url: Optional[str] = None, timeout: int = 30):
        """
        APIClient 생성자
        
        Args:
            base_url: API 기본 URL
            timeout: API 요청 타임아웃 (초)
        """
        self.base_url = base_url or os.getenv("API_URL", "http://localhost:8000/api/v1")
        self.timeout = timeout
        self.session = requests.Session()
    
    def _make_request(
        self, 
        method: str, 
        endpoint: str, 
        params: Optional[Dict[str, Any]] = None,
        data: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """
        API 요청을 보내고 응답을 처리합니다.
        
        Args:
            method: HTTP 메서드 (GET, POST, PUT, DELETE)
            endpoint: API 엔드포인트
            params: URL 쿼리 파라미터
            data: 요청 본문 데이터
            headers: HTTP 헤더
            
        Returns:
            API 응답 데이터
            
        Raises:
            APIError: API 요청 중 오류 발생 시
        """
        url = f"{self.base_url}{endpoint}"
        default_headers = {"Accept": "application/json"}
        
        if headers:
            default_headers.update(headers)
        
        # 파라미터에서 None 값 제거
        if params:
            params = {k: v for k, v in params.items() if v is not None}
        
        try:
            # HTTP 메서드에 따라 요청 보내기
            if method.upper() == "GET":
                response = self.session.get(
                    url, 
                    params=params, 
                    headers=default_headers,
                    timeout=self.timeout
                )
            elif method.upper() == "POST":
                response = self.session.post(
                    url, 
                    params=params, 
                    json=data, 
                    headers=default_headers,
                    timeout=self.timeout
                )
            elif method.upper() == "PUT":
                response = self.session.put(
                    url, 
                    params=params, 
                    json=data, 
                    headers=default_headers,
                    timeout=self.timeout
                )
            elif method.upper() == "DELETE":
                response = self.session.delete(
                    url, 
                    params=params, 
                    headers=default_headers,
                    timeout=self.timeout
                )
            else:
                raise ValueError(f"지원하지 않는 HTTP 메서드: {method}")
            
            # 응답 상태 코드 확인
            response.raise_for_status()
            
            # JSON 응답 파싱
            return response.json()
        
        except requests.exceptions.HTTPError as e:
            # HTTP 오류 처리
            error_msg = f"HTTP 오류: {e}"
            try:
                error_data = response.json()
                if "detail" in error_data:
                    error_msg = f"API 오류: {error_data['detail']}"
            except:
                pass
            
            raise APIError(error_msg)
        
        except requests.exceptions.ConnectionError:
            raise APIError("API 서버에 연결할 수 없습니다. 서버가 실행 중인지 확인하세요.")
        
        except requests.exceptions.Timeout:
            raise APIError(f"API 요청 시간이 초과되었습니다. (타임아웃: {self.timeout}초)")
        
        except requests.exceptions.RequestException as e:
            raise APIError(f"API 요청 중 오류가 발생했습니다: {str(e)}")
        
        except ValueError as e:
            raise APIError(f"응답 데이터 처리 중 오류가 발생했습니다: {str(e)}")
    
    @st.cache_data(ttl=300)
    def get_categories(self) -> List[str]:
        """
        뉴스 카테고리 목록을 가져옵니다.
        
        Returns:
            카테고리 목록
            
        Raises:
            APIError: API 요청 중 오류 발생 시
        """
        response = self._make_request("GET", "/categories")
        return response or []
    
    @st.cache_data(ttl=300)
    def get_stats(self) -> Dict[str, Any]:
        """
        전체 통계 데이터를 가져옵니다.
        
        Returns:
            통계 데이터
            
        Raises:
            APIError: API 요청 중 오류 발생 시
        """
        response = self._make_request("GET", "/stats")
        return response or {}
    
    @st.cache_data(ttl=300)
    def get_stats_summary(self, start_date: Optional[str] = None, end_date: Optional[str] = None, days: Optional[int] = None) -> Dict[str, Any]:
        """
        전체 통계 요약 데이터를 가져옵니다.
        
        Args:
            start_date: 시작일 (ISO 형식)
            end_date: 종료일 (ISO 형식)
            days: 최근 일수 (start_date와 end_date가 없을 경우 사용)
            
        Returns:
            통계 요약 데이터
            
        Raises:
            APIError: API 요청 중 오류 발생 시
        """
        params = {
            "start_date": start_date,
            "end_date": end_date,
            "days": days
        }
        
        response = self._make_request("GET", "/stats/summary", params=params)
        result = response or {}
        
        # 감성 분포 퍼센트 계산 추가
        if result and "categories" in result:
            total_sentiments = 0
            positive = 0
            neutral = 0
            negative = 0
            
            for category in result.get("categories", []):
                sentiment_dist = category.get("sentiment_distribution", {})
                positive += sentiment_dist.get("positive", 0)
                neutral += sentiment_dist.get("neutral", 0)
                negative += sentiment_dist.get("negative", 0)
            
            total_sentiments = positive + neutral + negative
            
            if total_sentiments > 0:
                result["positive_percent"] = round(positive / total_sentiments * 100, 1)
                result["neutral_percent"] = round(neutral / total_sentiments * 100, 1)
                result["negative_percent"] = round(negative / total_sentiments * 100, 1)
            else:
                result["positive_percent"] = 0
                result["neutral_percent"] = 0
                result["negative_percent"] = 0
        
        # 시간 범위 정보 추가
        if "time_range" not in result:
            if start_date and end_date:
                result["time_range"] = {
                    "start": start_date,
                    "end": end_date
                }
            elif days:
                result["time_range"] = {
                    "start": datetime.now() - timedelta(days=days),
                    "end": datetime.now()
                }
            else:
                result["time_range"] = {
                    "start": datetime.now() - timedelta(days=7),
                    "end": datetime.now()
                }
        
        return result
    
    @st.cache_data(ttl=300)
    def get_category_summary(self, start_date: Optional[str] = None, end_date: Optional[str] = None, days: Optional[int] = None) -> Dict[str, Any]:
        """
        카테고리별 통계 요약 데이터를 가져옵니다.
        
        Args:
            start_date: 시작일 (ISO 형식)
            end_date: 종료일 (ISO 형식)
            days: 최근 일수 (start_date와 end_date가 없을 경우 사용)
            
        Returns:
            카테고리 통계 요약 데이터
            
        Raises:
            APIError: API 요청 중 오류 발생 시
        """
        params = {
            "start_date": start_date,
            "end_date": end_date,
            "days": days
        }
        
        response = self._make_request("GET", "/categories/summary", params=params)
        return response or {}
    
    @st.cache_data(ttl=300)
    def get_article_timeline(
        self, 
        category: Optional[str] = None,
        sentiment: Optional[str] = None,
        days: int = 30,
        interval: str = "day"
    ) -> Dict[str, Any]:
        """
        시간별 기사 개수 타임라인 데이터를 가져옵니다.
        
        Args:
            category: 카테고리 (선택 사항)
            sentiment: 감성 (선택 사항)
            days: 최근 일수
            interval: 시간 간격 (hour, day, week)
            
        Returns:
            타임라인 데이터
            
        Raises:
            APIError: API 요청 중 오류 발생 시
        """
        params = {
            "category": category,
            "sentiment": sentiment,
            "days": days,
            "interval": interval
        }
        
        response = self._make_request("GET", "/timeline/articles", params=params)
        return response or {}
    
    @st.cache_data(ttl=300)
    def get_articles(
        self,
        category: Optional[str] = None,
        keyword: Optional[str] = None,
        sentiment: Optional[str] = None,
        topic: Optional[str] = None,
        days: Optional[int] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        limit: int = 10,
        offset: int = 0,
        sort_by: str = "published_at",
        sort_order: str = "desc"
    ) -> Dict[str, Any]:
        """
        뉴스 기사 목록을 가져옵니다.
        
        Args:
            category: 카테고리 (선택 사항)
            keyword: 키워드 (선택 사항)
            sentiment: 감성 (선택 사항)
            topic: 토픽 (선택 사항)
            days: 최근 일수 (선택 사항)
            start_date: 시작일 (선택 사항, ISO 형식)
            end_date: 종료일 (선택 사항, ISO 형식)
            limit: 결과 개수 제한
            offset: 결과 오프셋
            sort_by: 정렬 기준 필드
            sort_order: 정렬 방향 (asc, desc)
            
        Returns:
            뉴스 기사 목록
            
        Raises:
            APIError: API 요청 중 오류 발생 시
        """
        params = {
            "category": category,
            "keyword": keyword,
            "sentiment": sentiment,
            "topic": topic,
            "days": days,
            "start_date": start_date,
            "end_date": end_date,
            "limit": limit,
            "offset": offset,
            "sort_by": sort_by,
            "sort_order": sort_order
        }
        
        response = self._make_request("GET", "/articles", params=params)
        return response or {}
    
    @st.cache_data(ttl=300)
    def search_articles(
        self,
        query: Optional[str] = None,
        category: Optional[str] = None,
        sentiment: Optional[str] = None,
        days: Optional[int] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        page: int = 1,
        items_per_page: int = 10,
        sort: Optional[str] = None,
        sort_direction: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        뉴스 기사를 검색합니다.
        
        Args:
            query: 검색어 (선택 사항)
            category: 카테고리 (선택 사항)
            sentiment: 감성 (선택 사항)
            days: 최근 일수 (선택 사항)
            start_date: 시작일 (선택 사항, ISO 형식)
            end_date: 종료일 (선택 사항, ISO 형식)
            page: 페이지 번호
            items_per_page: 페이지 크기
            sort: 정렬 기준 필드
            sort_direction: 정렬 방향 (asc, desc)
            
        Returns:
            검색 결과
            
        Raises:
            APIError: API 요청 중 오류 발생 시
        """
        search_data = {
            "query": query,
            "category": category,
            "sentiment": sentiment,
            "days": days,
            "start_date": start_date,
            "end_date": end_date,
            "page": page,
            "size": items_per_page,  # API는 여전히 'size' 파라미터를 사용
            "sort_by": sort,
            "sort_order": sort_direction
        }
        
        # None 값 제거
        search_data = {k: v for k, v in search_data.items() if v is not None}
        
        response = self._make_request("POST", "/search", data=search_data)
        return response or {}
    
    @st.cache_data(ttl=300)
    def get_article_by_id(self, article_id: str) -> Dict[str, Any]:
        """
        기사 ID로 상세 정보를 가져옵니다.
        
        Args:
            article_id: 기사 ID
            
        Returns:
            기사 상세 정보
            
        Raises:
            APIError: API 요청 중 오류 발생 시
        """
        response = self._make_request("GET", f"/articles/{article_id}")
        return response or {}
    
    @st.cache_data(ttl=300)
    def get_articles_by_topic(
        self, 
        topic: str,
        category: Optional[str] = None,
        days: Optional[int] = None,
        limit: int = 10
    ) -> Dict[str, Any]:
        """
        특정 토픽의 기사 목록을 가져옵니다.
        
        Args:
            topic: 토픽
            category: 카테고리 (선택 사항)
            days: 최근 일수 (선택 사항)
            limit: 결과 개수 제한
            
        Returns:
            토픽별 기사 목록
            
        Raises:
            APIError: API 요청 중 오류 발생 시
        """
        params = {
            "topic": topic,
            "category": category,
            "days": days,
            "limit": limit
        }
        
        response = self._make_request("GET", "/topics/articles", params=params)
        return response or {}
    
    @st.cache_data(ttl=300)
    def get_trending_keywords(
        self,
        category: Optional[str] = None,
        days: Optional[int] = None,
        limit: int = 20
    ) -> Dict[str, Any]:
        """
        트렌딩 키워드 목록을 가져옵니다.
        
        Args:
            category: 카테고리 (선택 사항)
            days: 최근 일수 (선택 사항)
            limit: 결과 개수 제한
            
        Returns:
            트렌딩 키워드 목록
            
        Raises:
            APIError: API 요청 중 오류 발생 시
        """
        params = {
            "category": category,
            "days": days,
            "limit": limit
        }
        
        response = self._make_request("GET", "/keywords/trending", params=params)
        return response or {}
    
    @st.cache_data(ttl=300)
    def get_keyword_network(
        self,
        keyword: str,
        depth: int = 1,
        days: Optional[int] = None,
        category: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        키워드 네트워크 데이터를 가져옵니다.
        
        Args:
            keyword: 키워드
            depth: 네트워크 깊이
            days: 최근 일수 (선택 사항)
            category: 카테고리 (선택 사항)
            
        Returns:
            키워드 네트워크 데이터
            
        Raises:
            APIError: API 요청 중 오류 발생 시
        """
        params = {
            "keyword": keyword,
            "depth": depth,
            "days": days,
            "category": category
        }
        
        response = self._make_request("GET", "/keywords/network", params=params)
        return response or {}
    
    @st.cache_data(ttl=300)
    def get_sentiment_distribution(
        self,
        category: Optional[str] = None,
        days: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        감성 분포 데이터를 가져옵니다.
        
        Args:
            category: 카테고리 (선택 사항)
            days: 최근 일수 (선택 사항)
            
        Returns:
            감성 분포 데이터
            
        Raises:
            APIError: API 요청 중 오류 발생 시
        """
        params = {
            "category": category,
            "days": days
        }
        
        response = self._make_request("GET", "/sentiment/distribution", params=params)
        return response or {}
    
    @st.cache_data(ttl=300)
    def get_sentiment_trends(
        self,
        interval: str = "day",
        category: Optional[str] = None,
        days: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        시간별 감성 트렌드 데이터를 가져옵니다.
        
        Args:
            interval: 시간 간격 (hour, day, week)
            category: 카테고리 (선택 사항)
            days: 최근 일수 (선택 사항)
            
        Returns:
            감성 트렌드 데이터
            
        Raises:
            APIError: API 요청 중 오류 발생 시
        """
        params = {
            "interval": interval,
            "category": category,
            "days": days
        }
        
        response = self._make_request("GET", "/sentiment/trends", params=params)
        result = response or {}
        
        # 응답 데이터 처리
        if "points" in result:
            # 점수를 비율로 변환
            for point in result["points"]:
                timestamp = point.get("timestamp")
                total = sum(point.get("counts", {}).values())
                
                # 빈 포인트 처리
                if timestamp and total > 0:
                    point["ratios"] = {
                        k: round(v / total * 100, 1) for k, v in point.get("counts", {}).items()
                    }
                else:
                    point["ratios"] = {
                        "positive": 0,
                        "neutral": 0,
                        "negative": 0
                    }
        
        return result
    
    @st.cache_data(ttl=300)
    def get_sentiment_by_category(
        self,
        days: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        카테고리별 감성 분포 데이터를 가져옵니다.
        
        Args:
            days: 최근 일수 (선택 사항)
            
        Returns:
            카테고리별 감성 분포 데이터
            
        Raises:
            APIError: API 요청 중 오류 발생 시
        """
        params = {
            "days": days
        }
        
        response = self._make_request("GET", "/sentiment/categories", params=params)
        return response or {}
    
    @st.cache_data(ttl=300)
    def get_topic_distribution(
        self,
        category: Optional[str] = None,
        days: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        토픽 분포 데이터를 가져옵니다.
        
        Args:
            category: 카테고리 (선택 사항)
            days: 최근 일수 (선택 사항)
            
        Returns:
            토픽 분포 데이터
            
        Raises:
            APIError: API 요청 중 오류 발생 시
        """
        params = {
            "category": category,
            "days": days
        }
        
        response = self._make_request("GET", "/topics/distribution", params=params)
        return response or {}
    
    @st.cache_data(ttl=300)
    def get_topic_trends(
        self,
        interval: str = "day",
        category: Optional[str] = None,
        days: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        시간별 토픽 트렌드 데이터를 가져옵니다.
        
        Args:
            interval: 시간 간격 (hour, day, week)
            category: 카테고리 (선택 사항)
            days: 최근 일수 (선택 사항)
            
        Returns:
            토픽 트렌드 데이터
            
        Raises:
            APIError: API 요청 중 오류 발생 시
        """
        params = {
            "interval": interval,
            "category": category,
            "days": days
        }
        
        response = self._make_request("GET", "/topics/trends", params=params)
        return response or {}
    
    @st.cache_data(ttl=300)
    def get_topic_keywords(
        self,
        category: Optional[str] = None,
        days: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        토픽별 키워드 데이터를 가져옵니다.
        
        Args:
            category: 카테고리 (선택 사항)
            days: 최근 일수 (선택 사항)
            
        Returns:
            토픽별 키워드 데이터
            
        Raises:
            APIError: API 요청 중 오류 발생 시
        """
        params = {
            "category": category,
            "days": days
        }
        
        response = self._make_request("GET", "/topics/keywords", params=params)
        return response or {}
    
    def clear_cache(self) -> None:
        """모든 캐시된 API 호출을 무효화합니다."""
        self.get_categories.clear()
        self.get_stats.clear()
        self.get_stats_summary.clear()
        self.get_category_summary.clear()
        self.get_article_timeline.clear()
        self.get_articles.clear()
        self.search_articles.clear()
        self.get_article_by_id.clear()
        self.get_articles_by_topic.clear()
        self.get_trending_keywords.clear()
        self.get_keyword_network.clear()
        self.get_sentiment_distribution.clear()
        self.get_sentiment_trends.clear()
        self.get_sentiment_by_category.clear()
        self.get_topic_distribution.clear()
        self.get_topic_trends.clear()
        self.get_topic_keywords.clear() 