"""
뉴스 기사 Repository 구현 (비동기 지원)

이 모듈은 뉴스 기사 관련 컬렉션에 대한 특화된 비동기 Repository 클래스를 제공합니다.
"""

from typing import Dict, List, Any, Optional, Union, Tuple, Type
from datetime import datetime, timedelta, timezone

from motor.motor_asyncio import AsyncIOMotorDatabase

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


class ArticleRepository(BaseRepository[Dict[str, Any]]):
    """기본 기사 리포지토리 (특정 컬렉션 없이 일반적인 기사 관련 작업용)"""
    # 이 클래스는 특정 컬렉션에 바인딩되지 않으므로, collection_name을 필요로 하지 않음.
    # 또는, 자식 클래스에서 collection_name을 지정하도록 강제할 수 있음.
    # 현재 BaseRepository는 collection_name을 필수로 받으므로, 이 클래스 사용 방식 재고 필요.
    # 우선은 임시로 기본값을 넣어두거나, 혹은 이 클래스를 추상 클래스처럼 사용하고
    # 실제 인스턴스화는 자식 클래스에서만 하도록 유도.
    def __init__(self, db_session: AsyncIOMotorDatabase, collection_name: Union[str, CollectionName] = "articles_default"): # 임시 기본값
        super().__init__(db_session=db_session, collection_name=collection_name)

    async def save_article(self, article: Union[Dict[str, Any], BaseModel]) -> str:
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
            # datetime.now().isoformat() 대신 timezone-aware datetime 사용 고려
            article_dict[processed_time_field] = datetime.utcnow().isoformat() + "Z"
        
        try:
            # URL 기준으로 upsert
            await self.update_one(
                {"url": article_dict["url"]},
                article_dict,
                upsert=True
            )
            
            return article_dict["url"]
        except Exception as e:
            # OperationError의 cause로 원래 예외를 전달하는 것이 좋음
            raise OperationError("save_article (async)", self.collection_name, {"url": article_dict.get("url")}, e)
    
    async def get_article_by_url(self, url: str) -> Optional[Dict[str, Any]]:
        """URL로 기사를 조회합니다."""
        return await self.find_one({"url": url})
    
    async def get_articles_by_category(
        self, category: str, limit: int = 10, skip: int = 0
    ) -> List[Dict[str, Any]]:
        """카테고리별 기사 목록을 조회합니다."""
        return await self.find_many(
            filter_query={"category": category},
            sort_key="published_at",
            sort_order=-1,
            limit=limit,
            skip=skip,
        )
    
    async def get_articles_by_date_range(
        self, start_date: datetime, end_date: datetime, limit: int = 0, skip: int = 0
    ) -> List[Dict[str, Any]]:
        """날짜 범위로 기사를 조회합니다."""
        # 날짜 범위를 ISO 형식 문자열로 변환 (시간대 정보 포함)
        query = {
            "published_at": {
                "$gte": start_date.astimezone(timezone.utc).isoformat(),
                "$lte": end_date.astimezone(timezone.utc).isoformat(),
            }
        }
        return await self.find_many(
            filter_query=query,
            sort_key="published_at",
            sort_order=-1,
            limit=limit,
            skip=skip
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
    """수집된 원본 기사 리포지토리"""
    def __init__(self, db_session: AsyncIOMotorDatabase):
        super().__init__(db_session=db_session, collection_name=CollectionName.RAW_ARTICLES)
        self.model_class = NewsArticleModel
    
    def _get_processed_time_field(self) -> Optional[str]:
        return "collected_at"


class ProcessedArticleRepository(ArticleRepository):
    """1차 처리된 기사 리포지토리 (키워드, 토픽 등)"""
    def __init__(self, db_session: AsyncIOMotorDatabase):
        super().__init__(db_session=db_session, collection_name=CollectionName.PROCESSED_ARTICLES)
        self.model_class = ProcessedArticleModel
        self.raw_repo = RawArticleRepository(db_session=db_session)
    
    def _get_processed_time_field(self) -> Optional[str]:
        return "processed_at"
    
    async def get_unprocessed_articles(self, limit: int = 100) -> List[Dict[str, Any]]:
        """처리되지 않은 원본 기사를 조회합니다. (ProcessedArticle에 없는 기사)"""
        # 성능을 위해 lookup 대신 Python 레벨에서 차집합을 구하거나,
        # RawArticle에 'is_processed' 같은 플래그를 두는 것을 고려.
        # 현재는 ProcessedArticle에 있는 URL 목록을 가져와서, RawArticle에서 해당 URL들을 제외하는 방식.

        processed_article_urls = await self.find_many(
            projection={"url": 1, "_id": 0}, limit=0 # 모든 URL 가져오기
        )
        processed_urls_set = {article["url"] for article in processed_article_urls if "url" in article}

        # RawArticleRepository를 사용하여 처리되지 않은 기사 조회
        # RawArticleRepository 인스턴스 생성 시 db_session 전달
        
        unprocessed_articles = await self.raw_repo.find_many(
            filter_query={"url": {"$nin": list(processed_urls_set)}},
            limit=limit,
            sort_key="collected_at", # 수집된 순서대로
            sort_order=1 
        )
        return unprocessed_articles
    
    async def mark_as_processed(self, article_url: str) -> None:
        """특정 기사를 처리 완료로 표시 (실제로는 ProcessedArticle에 저장함으로써 간접 표시)"""
        # 이 메소드는 실제로는 ProcessedArticle을 생성(create)하는 로직으로 대체될 수 있습니다.
        # 또는, RawArticle에 'status' 필드를 업데이트 할 수도 있습니다.
        # 현재 구조에서는 ProcessedArticleRepository가 RawArticle의 상태를 직접 변경하는 것은
        # 책임 분리 원칙에 어긋날 수 있습니다.
        # 여기서는 개념적인 메소드로 남겨두거나, 다른 방식으로 구현해야 합니다.
        pass # 실제 구현은 서비스 레이어나 다른 곳에서 처리


class SentimentArticleRepository(ArticleRepository):
    """감성 분석된 기사 리포지토리"""
    def __init__(self, db_session: AsyncIOMotorDatabase):
        super().__init__(db_session=db_session, collection_name=CollectionName.SENTIMENT_ARTICLES)
        self.model_class = SentimentArticleModel
    
    def _get_processed_time_field(self) -> Optional[str]:
        return "sentiment_processed_at"
    
    async def get_articles_by_sentiment(
        self, sentiment: str, limit: int = 10, skip: int = 0
    ) -> List[Dict[str, Any]]:
        """특정 감성으로 분석된 기사 목록을 조회합니다."""
        return await self.find_many(
            filter_query={"sentiment_analysis.overall_sentiment.sentiment": sentiment},
            sort_key="published_at",
            sort_order=-1,
            limit=limit,
            skip=skip,
        )
    
    async def get_sentiment_distribution(
        self, category: Optional[str] = None, days: int = 7
    ) -> Dict[str, int]:
        """카테고리별 또는 전체 감성 분포를 조회합니다."""
        match_query: Dict[str, Any] = {}
        if category:
            match_query["category"] = category
        
        if days > 0:
            start_dt = datetime.now(timezone.utc) - timedelta(days=days)
            match_query["published_at"] = {"$gte": start_dt.isoformat()}

        pipeline = [
            {"$match": match_query},
            {"$group": {
                "_id": "$sentiment_analysis.overall_sentiment.sentiment",
                "count": {"$sum": 1}
            }}
        ]
        
        raw_result = await self.aggregate(pipeline)
        
        distribution = {"positive": 0, "neutral": 0, "negative": 0}
        for item in raw_result:
            sentiment_value = item.get("_id")
            if sentiment_value in distribution: # null이나 예상 못한 값 제외
                distribution[sentiment_value] = item.get("count", 0)
        
        return distribution


class SummaryArticleRepository(ArticleRepository):
    """요약된 기사 리포지토리"""
    def __init__(self, db_session: AsyncIOMotorDatabase):
        super().__init__(db_session=db_session, collection_name=CollectionName.SUMMARY_ARTICLES)
        self.model_class = SummaryArticleModel
    
    def _get_processed_time_field(self) -> Optional[str]:
        return "summary_processed_at"
    
    async def get_latest_summaries(
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
        
        return await self.find_many(
            query,
            sort_key="published_at",
            sort_order=-1,
            limit=limit
        ) 