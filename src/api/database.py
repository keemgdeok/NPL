from typing import List, Dict, Any, Optional, Union, Tuple
from datetime import datetime, timedelta
from bson import ObjectId
import re
from collections import Counter, defaultdict

from ..collectors.utils.config import Config
from ..common.database.repositories.article_repository import (
    SentimentArticleRepository,
    RawArticleRepository,
    ProcessedArticleRepository,
    SummaryArticleRepository
)
from ..common.database.exceptions import OperationError


class Database:
    def __init__(self):
        """데이터베이스 초기화
        
        Repository 패턴을 사용하여 MongoDB 접근을 캡슐화합니다.
        """
        self.sentiment_repo = SentimentArticleRepository()
        self.raw_repo = RawArticleRepository()
        self.processed_repo = ProcessedArticleRepository()
        self.summary_repo = SummaryArticleRepository()
    
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
        total = self.sentiment_repo.count(query)
        
        # 페이지네이션 적용하여 데이터 조회
        articles = self.sentiment_repo.find_many(
            query=query,
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
    
    def get_article_by_url(self, url: str) -> Optional[Dict[str, Any]]:
        """URL로 기사 상세 조회"""
        return self.sentiment_repo.find_one({"url": url})
    
    def get_category_summary(
        self,
        category: str,
        days: int = 7
    ) -> Optional[Dict[str, Any]]:
        """카테고리별 통계 요약"""
        start_date = datetime.now() - timedelta(days=days)
        
        # 감성 분포 집계
        sentiment_distribution = self.sentiment_repo.get_sentiment_distribution(
            category=category,
            days=days
        )
        
        # 토픽 분포 집계
        match_stage = {
                "category": category,
                "published_at": {"$gte": start_date.isoformat()}
            }
        
        pipeline = [
            {"$match": match_stage},
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
        ]
        
        topic_distribution = self.sentiment_repo.aggregate(pipeline)
        
        # 전체 기사 수
        article_count = self.sentiment_repo.count({
            "category": category,
            "published_at": {"$gte": start_date.isoformat()}
        })
        
        return {
            "category": category,
            "article_count": article_count,
            "sentiment_distribution": sentiment_distribution,
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
        total_articles = self.sentiment_repo.count({
            "published_at": {"$gte": start_date.isoformat()}
        })
        
        # 카테고리별 요약
        categories = []
        for category in Config.CATEGORIES.keys():
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
    
    # 추가: 시간별 기사 수 조회
    def get_article_timeline(
        self, 
        category: Optional[str] = None,
        sentiment: Optional[str] = None, 
        days: int = 30, 
        interval: str = "day"
    ) -> Dict[str, Any]:
        """시간별 기사 수 조회
        
        Args:
            category: 카테고리 (선택적)
            sentiment: 감성 (선택적)
            days: 조회 기간 (일)
            interval: 시간 간격 ('hour', 'day', 'week')
            
        Returns:
            Dict: 시간별 기사 수 데이터
        """
        start_date = datetime.now() - timedelta(days=days)
        
        # 쿼리 조건 구성
        match_stage = {"published_at": {"$gte": start_date.isoformat()}}
        if category:
            match_stage["category"] = category
        if sentiment:
            match_stage["sentiment_analysis.overall_sentiment.sentiment"] = sentiment
        
        # 시간 간격에 따른 그룹핑 설정
        if interval == "hour":
            group_format = "%Y-%m-%d-%H"
            date_format = {"$dateToString": {"format": group_format, "date": {"$dateFromString": {"dateString": "$published_at"}}}}
        elif interval == "week":
            group_format = "%Y-%U"  # ISO 주 형식
            date_format = {"$dateToString": {"format": group_format, "date": {"$dateFromString": {"dateString": "$published_at"}}}}
        else:  # 기본값: day
            group_format = "%Y-%m-%d"
            date_format = {"$dateToString": {"format": group_format, "date": {"$dateFromString": {"dateString": "$published_at"}}}}
        
        # 집계 파이프라인
        pipeline = [
            {"$match": match_stage},
            {"$group": {
                "_id": date_format,
                "count": {"$sum": 1}
            }},
            {"$sort": {"_id": 1}}
        ]
        
        result = self.sentiment_repo.aggregate(pipeline)
        
        # 결과 가공
        timeline_data = []
        total_count = 0
        
        for item in result:
            # 날짜 파싱 (간격별로 처리)
            if interval == "hour":
                # YYYY-MM-DD-HH 형식 파싱
                date_parts = item["_id"].split("-")
                if len(date_parts) >= 4:
                    dt = datetime(int(date_parts[0]), int(date_parts[1]), int(date_parts[2]), int(date_parts[3]))
                else:
                    continue
            elif interval == "week":
                # YYYY-WW 형식 파싱 (주 단위)
                date_parts = item["_id"].split("-")
                if len(date_parts) >= 2:
                    year, week = int(date_parts[0]), int(date_parts[1])
                    dt = datetime.strptime(f"{year}-{week}-1", "%Y-%W-%w")
                else:
                    continue
            else:  # 일 단위
                # YYYY-MM-DD 형식 파싱
                try:
                    dt = datetime.strptime(item["_id"], "%Y-%m-%d")
                except ValueError:
                    continue
            
            count = item["count"]
            total_count += count
            
            timeline_data.append({
                "timestamp": dt,
                "count": count
            })
        
        # 필요시 결측치 채우기
        if interval == "day" and len(timeline_data) < days:
            filled_data = []
            current_date = start_date.replace(hour=0, minute=0, second=0, microsecond=0)
            end_date = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
            
            # 일별 데이터 사전 생성
            date_dict = {item["timestamp"]: item["count"] for item in timeline_data}
            
            # 모든 날짜에 대해 데이터 채우기
            while current_date <= end_date:
                count = date_dict.get(current_date, 0)
                filled_data.append({
                    "timestamp": current_date,
                    "count": count
                })
                current_date += timedelta(days=1)
            
            timeline_data = filled_data
        
        return {
            "interval": interval,
            "data": timeline_data,
            "category": category,
            "sentiment": sentiment,
            "total": total_count,
            "time_range": {
                "start": start_date,
                "end": datetime.now()
            }
        }
    
    # 추가: 감성 트렌드 조회
    def get_sentiment_trends(
        self, 
        category: Optional[str] = None, 
        days: int = 30, 
        interval: str = "day"
    ) -> Dict[str, Any]:
        """감성 트렌드 조회
        
        Args:
            category: 카테고리 (선택적)
            days: 조회 기간 (일)
            interval: 시간 간격 ('hour', 'day', 'week')
            
        Returns:
            Dict: 시간별 감성 분포 데이터
        """
        start_date = datetime.now() - timedelta(days=days)
        
        # 쿼리 조건 구성
        match_stage = {"published_at": {"$gte": start_date.isoformat()}}
        if category:
            match_stage["category"] = category
        
        # 시간 간격에 따른 그룹핑 설정
        if interval == "hour":
            group_format = "%Y-%m-%d-%H"
            date_format = {"$dateToString": {"format": group_format, "date": {"$dateFromString": {"dateString": "$published_at"}}}}
        elif interval == "week":
            group_format = "%Y-%U"  # ISO 주 형식
            date_format = {"$dateToString": {"format": group_format, "date": {"$dateFromString": {"dateString": "$published_at"}}}}
        else:  # 기본값: day
            group_format = "%Y-%m-%d"
            date_format = {"$dateToString": {"format": group_format, "date": {"$dateFromString": {"dateString": "$published_at"}}}}
        
        # 집계 파이프라인
        pipeline = [
            {"$match": match_stage},
            {"$group": {
                "_id": {
                    "time": date_format,
                    "sentiment": "$sentiment_analysis.overall_sentiment.sentiment"
                },
                "count": {"$sum": 1}
            }},
            {"$sort": {"_id.time": 1}}
        ]
        
        result = self.sentiment_repo.aggregate(pipeline)
        
        # 결과 가공
        sentiment_data = defaultdict(lambda: {"positive": 0, "neutral": 0, "negative": 0, "total": 0})
        
        for item in result:
            time_key = item["_id"]["time"]
            sentiment = item["_id"]["sentiment"]
            count = item["count"]
            
            if sentiment not in ["positive", "neutral", "negative"]:
                sentiment = "neutral"  # 알 수 없는 감성은 중립으로 처리
            
            sentiment_data[time_key][sentiment] += count
            sentiment_data[time_key]["total"] += count
        
        # 시간별 데이터 생성
        timeline_data = []
        total_count = 0
        
        for time_key, counts in sorted(sentiment_data.items()):
            # 날짜 파싱 (간격별로 처리)
            if interval == "hour":
                # YYYY-MM-DD-HH 형식 파싱
                date_parts = time_key.split("-")
                if len(date_parts) >= 4:
                    dt = datetime(int(date_parts[0]), int(date_parts[1]), int(date_parts[2]), int(date_parts[3]))
                else:
                    continue
            elif interval == "week":
                # YYYY-WW 형식 파싱 (주 단위)
                date_parts = time_key.split("-")
                if len(date_parts) >= 2:
                    year, week = int(date_parts[0]), int(date_parts[1])
                    dt = datetime.strptime(f"{year}-{week}-1", "%Y-%W-%w")
                else:
                    continue
            else:  # 일 단위
                # YYYY-MM-DD 형식 파싱
                try:
                    dt = datetime.strptime(time_key, "%Y-%m-%d")
                except ValueError:
                    continue
            
            data_point = {
                "timestamp": dt,
                "positive": counts["positive"],
                "neutral": counts["neutral"],
                "negative": counts["negative"],
                "total": counts["total"]
            }
            
            timeline_data.append(data_point)
            total_count += counts["total"]
        
        # 필요시 결측치 채우기 (일 단위에만 적용)
        if interval == "day" and len(timeline_data) < days:
            filled_data = []
            current_date = start_date.replace(hour=0, minute=0, second=0, microsecond=0)
            end_date = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
            
            # 일별 데이터 사전 생성
            date_dict = {item["timestamp"]: item for item in timeline_data}
            
            # 모든 날짜에 대해 데이터 채우기
            while current_date <= end_date:
                if current_date in date_dict:
                    filled_data.append(date_dict[current_date])
                else:
                    filled_data.append({
                        "timestamp": current_date,
                        "positive": 0,
                        "neutral": 0,
                        "negative": 0,
                        "total": 0
                    })
                current_date += timedelta(days=1)
            
            timeline_data = filled_data
        
        return {
            "interval": interval,
            "data": timeline_data,
            "category": category,
            "total": total_count,
            "time_range": {
                "start": start_date,
                "end": datetime.now()
            }
        }
    
    # 추가: 트렌딩 키워드 조회
    def get_trending_keywords(
        self,
        category: Optional[str] = None,
        days: int = 7,
        limit: int = 20
    ) -> Dict[str, Any]:
        """트렌딩 키워드 조회
        
        Args:
            category: 카테고리 (선택적)
            days: 조회 기간 (일)
            limit: 반환할 키워드 수
            
        Returns:
            Dict: 트렌딩 키워드 정보
        """
        start_date = datetime.now() - timedelta(days=days)
        
        # 쿼리 조건 구성
        query = {"published_at": {"$gte": start_date.isoformat()}}
        if category:
            query["category"] = category
        
        # 기사 조회
        articles = self.processed_repo.find_many(query=query, limit=1000)
        
        # 키워드 빈도 계산
        keyword_counter = Counter()
        doc_frequency = Counter()  # 문서 빈도 (TF-IDF 계산용)
        
        for article in articles:
            # 기사의 키워드 추출
            keywords = article.get("keywords", [])
            if not keywords:
                continue
            
            # 문서별 키워드 카운트 (중복 제거)
            unique_keywords = set(keywords)
            for keyword in unique_keywords:
                doc_frequency[keyword] += 1
            
            # 전체 키워드 빈도 카운트
            for keyword in keywords:
                keyword_counter[keyword] += 1
        
        total_docs = len(articles)
        
        # 키워드 중요도 계산 (TF-IDF 기반)
        keyword_scores = []
        for keyword, count in keyword_counter.most_common(limit * 2):  # 더 많이 추출 후 필터링
            if len(keyword.strip()) < 2:  # 너무 짧은 키워드는 제외
                continue
                
            # TF-IDF 계산
            tf = count  # 단순 빈도
            idf = 1.0
            if doc_frequency[keyword] > 0:
                idf = 1.0 + (total_docs / doc_frequency[keyword])
            
            score = tf * idf
            
            # 감성 분포 계산 (선택적)
            sentiment_distribution = self._get_keyword_sentiment_distribution(keyword, category, days)
            
            keyword_scores.append({
                "keyword": keyword,
                "count": count,
                "score": score,
                "sentiment_distribution": sentiment_distribution
            })
        
        # 점수 기준으로 정렬
        keyword_scores.sort(key=lambda x: x["score"], reverse=True)
        
        # 상위 키워드만 반환
        top_keywords = keyword_scores[:limit]
        
        return {
            "keywords": top_keywords,
            "category": category,
            "total_articles": total_docs,
            "time_range": {
                "start": start_date,
                "end": datetime.now()
            }
        }
    
    # 추가: 키워드 네트워크 조회
    def get_keyword_network(
        self,
        keyword: str,
        depth: int = 1,
        days: int = 7
    ) -> Dict[str, Any]:
        """키워드 네트워크 조회
        
        Args:
            keyword: 기준 키워드
            depth: 연관 깊이 (1~3)
            days: 조회 기간 (일)
            
        Returns:
            Dict: 키워드 네트워크 데이터
        """
        start_date = datetime.now() - timedelta(days=days)
        
        # 쿼리 조건 구성
        query = {
            "published_at": {"$gte": start_date.isoformat()},
            "keywords": {"$in": [keyword]}
        }
        
        # 기사 조회
        articles = self.processed_repo.find_many(query=query, limit=200)
        
        # 노드와 엣지 저장용 컬렉션
        nodes = {keyword: {"id": keyword, "label": keyword, "size": 10, "score": 1.0}}
        edges = {}
        
        # 키워드 동시 출현 분석
        for article in articles:
            article_keywords = article.get("keywords", [])
            if not article_keywords:
                continue
            
            # 기준 키워드를 제외한 다른 키워드들과 관계 설정
            for related_keyword in article_keywords:
                if related_keyword == keyword:
                    continue
                
                # 노드 추가
                if related_keyword not in nodes:
                    nodes[related_keyword] = {
                        "id": related_keyword,
                        "label": related_keyword,
                        "size": 1,
                        "score": 0.5
                    }
                else:
                    nodes[related_keyword]["size"] += 1
                
                # 엣지 추가 (양방향)
                edge_key = f"{keyword}_{related_keyword}"
                if edge_key not in edges:
                    edges[edge_key] = {
                        "source": keyword,
                        "target": related_keyword,
                        "weight": 1
                    }
                else:
                    edges[edge_key]["weight"] += 1
        
        # 깊이가 2 이상인 경우에만 추가 확장
        if depth >= 2 and len(nodes) > 1:
            # 첫 번째 깊이에서 찾은 관련 키워드들
            related_keywords = [k for k in nodes.keys() if k != keyword]
            
            # 관련 키워드별로 연결 관계 추가
            for related_keyword in related_keywords[:10]:  # 상위 10개만 처리 (성능 고려)
                related_query = {
                    "published_at": {"$gte": start_date.isoformat()},
                    "keywords": {"$in": [related_keyword]}
                }
                
                related_articles = self.processed_repo.find_many(query=related_query, limit=50)
                
                for article in related_articles:
                    article_keywords = article.get("keywords", [])
                    if not article_keywords:
                        continue
                    
                    for second_keyword in article_keywords:
                        if second_keyword == related_keyword or second_keyword == keyword:
                            continue
                        
                        # 2차 노드 추가
                        if second_keyword not in nodes:
                            nodes[second_keyword] = {
                                "id": second_keyword,
                                "label": second_keyword,
                                "size": 1,
                                "score": 0.3
                            }
                        else:
                            nodes[second_keyword]["size"] += 0.5
                        
                        # 2차 엣지 추가
                        edge_key = f"{related_keyword}_{second_keyword}"
                        if edge_key not in edges:
                            edges[edge_key] = {
                                "source": related_keyword,
                                "target": second_keyword,
                                "weight": 0.5
                            }
                        else:
                            edges[edge_key]["weight"] += 0.5
                            
        # 노드 크기 정규화 (최대 20)
        max_size = max(node["size"] for node in nodes.values())
        if max_size > 0:
            for node in nodes.values():
                node["size"] = 1 + (node["size"] / max_size) * 19
        
        return {
            "nodes": list(nodes.values()),
            "edges": list(edges.values()),
            "root_keyword": keyword,
            "depth": depth,
            "time_range": {
                "start": start_date,
                "end": datetime.now()
            }
        }
    
    # 추가: 키워드에 대한 감성 분포 조회 (내부 헬퍼 메서드)
    def _get_keyword_sentiment_distribution(
        self,
        keyword: str,
        category: Optional[str] = None,
        days: int = 7
    ) -> Dict[str, int]:
        """키워드에 대한 감성 분포 조회
        
        Args:
            keyword: 키워드
            category: 카테고리 (선택적)
            days: 조회 기간 (일)
            
        Returns:
            Dict: 감성별 기사 수
        """
        start_date = datetime.now() - timedelta(days=days)
        
        # 쿼리 조건 구성
        query = {
            "published_at": {"$gte": start_date.isoformat()},
            "keywords": {"$in": [keyword]}
        }
        if category:
            query["category"] = category
        
        # 감성별 기사 수 집계
        pipeline = [
            {"$match": query},
            {"$group": {
                "_id": "$sentiment_analysis.overall_sentiment.sentiment",
                "count": {"$sum": 1}
            }}
        ]
        
        result = self.sentiment_repo.aggregate(pipeline)
        
        # 결과 가공
        sentiment_distribution = {"positive": 0, "neutral": 0, "negative": 0}
        
        for item in result:
            sentiment = item["_id"]
            if sentiment in sentiment_distribution:
                sentiment_distribution[sentiment] = item["count"]
        
        return sentiment_distribution
    
    # 추가: 고급 검색
    def search_articles(
        self,
        search_request: Dict[str, Any]
    ) -> Dict[str, Any]:
        """고급 검색
        
        Args:
            search_request: 검색 요청 (SearchRequest 모델)
            
        Returns:
            Dict: 검색 결과
        """
        # 쿼리 조건 구성
        query = {}
        
        # 검색어
        if search_request.get("query"):
            keywords = re.split(r'\s+', search_request["query"].lower())
            search_terms = []
            
            # 제목 검색
            if keywords:
                title_queries = []
                for keyword in keywords:
                    if len(keyword) >= 2:  # 너무 짧은 키워드는 제외
                        title_queries.append({"title": {"$regex": keyword, "$options": "i"}})
                
                if title_queries:
                    search_terms.append({"$or": title_queries})
            
            # 키워드 검색
            if keywords:
                search_terms.append({"keywords": {"$in": keywords}})
            
            if search_terms:
                query["$or"] = search_terms
        
        # 카테고리 필터
        if search_request.get("categories"):
            query["category"] = {"$in": search_request["categories"]}
        
        # 감성 필터
        if search_request.get("sentiments"):
            query["sentiment_analysis.overall_sentiment.sentiment"] = {"$in": search_request["sentiments"]}
        
        # 날짜 필터
        date_query = {}
        if search_request.get("start_date"):
            date_query["$gte"] = search_request["start_date"].isoformat()
        if search_request.get("end_date"):
            date_query["$lte"] = search_request["end_date"].isoformat()
        if date_query:
            query["published_at"] = date_query
        
        # 언론사 필터
        if search_request.get("press"):
            query["press"] = {"$in": search_request["press"]}
        
        # 포함 키워드 필터
        if search_request.get("include_keywords"):
            query["keywords"] = {"$all": search_request["include_keywords"]}
        
        # 제외 키워드 필터
        if search_request.get("exclude_keywords"):
            if "keywords" not in query:
                query["keywords"] = {}
            query["keywords"]["$nin"] = search_request["exclude_keywords"]
        
        # 페이지네이션 값
        page = search_request.get("page", 1)
        size = search_request.get("size", 20)
        
        # 전체 개수 조회
        total = self.sentiment_repo.count(query)
        
        # 검색 결과 조회
        articles = self.sentiment_repo.find_many(
            query=query,
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
    
    def close(self):
        """데이터베이스 연결 종료"""
        # Repository 패턴에서는 별도의 종료 처리가 필요 없음
        pass 