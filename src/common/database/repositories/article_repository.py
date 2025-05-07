"""
뉴스 기사 Repository 구현

이 모듈은 뉴스 기사 관련 컬렉션에 대한 특화된 Repository 클래스를 제공합니다.
"""

from typing import Dict, List, Any, Optional, Union, Tuple, Type
from datetime import datetime, timedelta

from ..repository import BaseRepository
from ..collections import CollectionName
from ..models import (
    NewsArticleModel, 
    ProcessedArticleModel,
    SentimentArticleModel, 
    SummaryArticleModel,
    model_to_doc,
    doc_to_model,
    BaseModel
)
from ..exceptions import OperationError


class ArticleRepository(BaseRepository):
    """뉴스 기사 Repository 기본 클래스
    
    모든 뉴스 기사 관련 Repository의 공통 기능을 제공합니다.
    """
    
    # 자식 클래스에서 재정의
    model_class = None
    
    def save_article(self, article: Union[Dict[str, Any], BaseModel]) -> str:
        """뉴스 기사 저장 (upsert)
        
        Args:
            article: 저장할 뉴스 기사 (딕셔너리 또는 모델)
            
        Returns:
            str: 저장된 문서의 URL
            
        Raises:
            OperationError: 저장 작업 실패 시
            ValueError: 모델 클래스가 지정되지 않은 경우
        """
        if self.model_class is None:
            raise ValueError("모델 클래스가 지정되지 않았습니다. 자식 클래스에서 model_class를 설정해주세요.")
            
        # 모델을 딕셔너리로 변환
        if isinstance(article, BaseModel):
            article_dict = model_to_doc(article)
        else:
            article_dict = article
        
        # 처리 시간 필드가 있는지 확인
        processed_time_field = self._get_processed_time_field()
        if processed_time_field and processed_time_field not in article_dict:
            article_dict[processed_time_field] = datetime.now().isoformat()
        
        try:
            # URL 기준으로 upsert
            self.update_one(
                {"url": article_dict["url"]},
                article_dict,
                upsert=True
            )
            
            return article_dict["url"]
        except Exception as e:
            raise OperationError("save_article", self.collection_name, {"url": article_dict.get("url")}, e)
    
    def get_article_by_url(self, url: str) -> Optional[Dict[str, Any]]:
        """URL로 기사 조회
        
        Args:
            url: 기사 URL
            
        Returns:
            Optional[Dict]: 조회된 기사 또는 None
        """
        return self.find_one({"url": url})
    
    def get_articles_by_category(
        self,
        category: str,
        days: int = 7,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """카테고리별 기사 조회
        
        Args:
            category: 카테고리
            days: 최근 며칠 동안의 기사 (기본값: 7)
            limit: 최대 반환 건수 (기본값: 100)
            
        Returns:
            List[Dict]: 조회된 기사 목록
        """
        start_date = datetime.now() - timedelta(days=days)
        
        return self.find_many(
            {
                "category": category,
                "published_at": {"$gte": start_date.isoformat()}
            },
            sort_key="published_at",
            sort_order=-1,
            limit=limit
        )
    
    def _get_processed_time_field(self) -> Optional[str]:
        """처리 시간 필드 이름 반환
        
        각 Repository 단계에 해당하는 처리 시간 필드를 반환합니다.
        자식 클래스에서 필요에 따라 재정의합니다.
        
        Returns:
            Optional[str]: 처리 시간 필드 이름 또는 None
        """
        return None


class RawArticleRepository(ArticleRepository):
    """원본 뉴스 기사 Repository"""
    
    def __init__(self):
        super().__init__(CollectionName.RAW_ARTICLES)
        self.model_class = NewsArticleModel
    
    def _get_processed_time_field(self) -> Optional[str]:
        return "collected_at"


class ProcessedArticleRepository(ArticleRepository):
    """텍스트 처리된 뉴스 기사 Repository"""
    
    def __init__(self):
        super().__init__(CollectionName.PROCESSED_ARTICLES)
        self.model_class = ProcessedArticleModel
    
    def _get_processed_time_field(self) -> Optional[str]:
        return "processed_at"
    
    def get_unprocessed_articles(self, limit: int = 100) -> List[Dict[str, Any]]:
        """텍스트 처리되지 않은 기사 조회
        
        Args:
            limit: 최대 반환 건수 (기본값: 100)
            
        Returns:
            List[Dict]: 처리되지 않은 기사 목록
        """
        # 원본 기사 컬렉션에서 처리된 기사 컬렉션에 없는 URL 기준으로 조회
        pipeline = [
            {
                "$lookup": {
                    "from": CollectionName.PROCESSED_ARTICLES.value,
                    "localField": "url",
                    "foreignField": "url",
                    "as": "processed"
                }
            },
            {"$match": {"processed": {"$size": 0}}},
            {"$limit": limit}
        ]
        
        # 집계 파이프라인 실행을 위해 raw_article 저장소 객체 생성
        raw_repo = RawArticleRepository()
        return raw_repo.aggregate(pipeline)


class SentimentArticleRepository(ArticleRepository):
    """감성 분석된 뉴스 기사 Repository"""
    
    def __init__(self):
        super().__init__(CollectionName.SENTIMENT_ARTICLES)
        self.model_class = SentimentArticleModel
    
    def _get_processed_time_field(self) -> Optional[str]:
        return "sentiment_processed_at"
    
    def get_articles_by_sentiment(
        self,
        sentiment: str,
        category: Optional[str] = None,
        days: int = 7,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """감성별 기사 조회
        
        Args:
            sentiment: 감성 ('positive', 'negative', 'neutral')
            category: 카테고리 (선택적)
            days: 최근 며칠 동안의 기사 (기본값: 7)
            limit: 최대 반환 건수 (기본값: 100)
            
        Returns:
            List[Dict]: 조회된 기사 목록
        """
        start_date = datetime.now() - timedelta(days=days)
        
        query = {
            "sentiment_analysis.overall_sentiment.sentiment": sentiment,
            "published_at": {"$gte": start_date.isoformat()}
        }
        
        if category:
            query["category"] = category
        
        return self.find_many(
            query,
            sort_key="published_at",
            sort_order=-1,
            limit=limit
        )
    
    def get_sentiment_distribution(
        self,
        category: Optional[str] = None,
        days: int = 7
    ) -> Dict[str, int]:
        """감성 분포 집계
        
        Args:
            category: 카테고리 (선택적)
            days: 최근 며칠 동안의 기사 (기본값: 7)
            
        Returns:
            Dict[str, int]: 감성별 기사 수 {'positive': n, 'negative': m, 'neutral': k}
        """
        start_date = datetime.now() - timedelta(days=days)
        
        match_stage = {
            "published_at": {"$gte": start_date.isoformat()}
        }
        
        if category:
            match_stage["category"] = category
        
        pipeline = [
            {"$match": match_stage},
            {
                "$group": {
                    "_id": "$sentiment_analysis.overall_sentiment.sentiment",
                    "count": {"$sum": 1}
                }
            }
        ]
        
        result = self.aggregate(pipeline)
        
        # 결과를 딕셔너리로 변환
        return {item["_id"]: item["count"] for item in result}


class SummaryArticleRepository(ArticleRepository):
    """요약된 뉴스 기사 Repository"""
    
    def __init__(self):
        super().__init__(CollectionName.SUMMARY_ARTICLES)
        self.model_class = SummaryArticleModel
    
    def _get_processed_time_field(self) -> Optional[str]:
        return "summary_processed_at"
    
    def get_latest_summaries(
        self,
        category: Optional[str] = None,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """최신 요약 기사 조회
        
        Args:
            category: 카테고리 (선택적)
            limit: 최대 반환 건수 (기본값: 10)
            
        Returns:
            List[Dict]: 조회된 기사 목록
        """
        query = {}
        
        if category:
            query["category"] = category
        
        return self.find_many(
            query,
            sort_key="published_at",
            sort_order=-1,
            limit=limit
        ) 