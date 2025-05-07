"""
MongoDB 컬렉션 및 인덱스 정의

이 모듈은 MongoDB 컬렉션 이름과 인덱스를 중앙 집중식으로 관리합니다.
"""

from typing import Dict, List, Tuple, Any, Union
from enum import Enum


class CollectionName(str, Enum):
    """MongoDB 컬렉션 이름 상수"""
    
    # 원본 뉴스 기사
    RAW_ARTICLES = "news_articles"
    
    # 텍스트 처리된 기사
    PROCESSED_ARTICLES = "processed_articles"
    
    # 감성 분석된 기사
    SENTIMENT_ARTICLES = "sentiment_articles"
    
    # 요약된 기사
    SUMMARY_ARTICLES = "summary_articles"


class CollectionInfo:
    """컬렉션 정보 및 인덱스 정의
    
    컬렉션 이름과 해당 컬렉션의 인덱스 정보를 함께 관리합니다.
    """
    
    def __init__(self, name: str, indexes: List[Tuple[Any, Dict[str, Any]]] = None):
        """
        Args:
            name: 컬렉션 이름
            indexes: 인덱스 정의 목록 [(키, 옵션), ...]
        """
        self.name = name
        self.indexes = indexes or []
    
    def add_index(self, keys, **options):
        """인덱스 추가
        
        Args:
            keys: 인덱스 키
            options: 인덱스 옵션
        """
        self.indexes.append((keys, options))
        return self


# 컬렉션 정보 정의
COLLECTIONS = {
    CollectionName.RAW_ARTICLES: CollectionInfo(CollectionName.RAW_ARTICLES.value)
        .add_index([("url", 1)], unique=True)
        .add_index([("category", 1), ("published_at", -1)]),
        
    CollectionName.PROCESSED_ARTICLES: CollectionInfo(CollectionName.PROCESSED_ARTICLES.value)
        .add_index([("url", 1)], unique=True)
        .add_index([("category", 1), ("published_at", -1)]),
        
    CollectionName.SENTIMENT_ARTICLES: CollectionInfo(CollectionName.SENTIMENT_ARTICLES.value)
        .add_index([("url", 1)], unique=True)
        .add_index([("category", 1), ("published_at", -1)])
        .add_index([("sentiment_analysis.overall_sentiment.sentiment", 1)]),
        
    CollectionName.SUMMARY_ARTICLES: CollectionInfo(CollectionName.SUMMARY_ARTICLES.value)
        .add_index([("url", 1)], unique=True)
        .add_index([("category", 1), ("published_at", -1)])
}


def get_collection_info(collection_enum: CollectionName) -> CollectionInfo:
    """컬렉션 정보 반환
    
    Args:
        collection_enum: 컬렉션 열거형 값
        
    Returns:
        CollectionInfo: 컬렉션 정보 객체
    """
    return COLLECTIONS.get(collection_enum)


def get_collection_name(collection_enum: CollectionName) -> str:
    """컬렉션 이름 반환
    
    Args:
        collection_enum: 컬렉션 열거형 값
        
    Returns:
        str: 컬렉션 이름 문자열
    """
    return collection_enum.value


def get_collection_indexes(collection_name_or_enum: Union[str, CollectionName]) -> List[Tuple[Any, Dict[str, Any]]]:
    """컬렉션의 인덱스 정의 반환
    
    Args:
        collection_name_or_enum: 컬렉션 이름 또는 열거형
        
    Returns:
        List[Tuple]: 인덱스 정의 목록
    """
    # 문자열인 경우 열거형으로 변환 시도
    if isinstance(collection_name_or_enum, str):
        try:
            collection_enum = CollectionName(collection_name_or_enum)
        except ValueError:
            # 일치하는 열거형 값이 없으면 빈 리스트 반환
            return []
    else:
        collection_enum = collection_name_or_enum
    
    collection_info = COLLECTIONS.get(collection_enum)
    return collection_info.indexes if collection_info else [] 