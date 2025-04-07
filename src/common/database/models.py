"""
MongoDB 데이터 모델

이 모듈은 MongoDB 문서의 데이터 모델을 정의합니다.
Pydantic을 사용하여 문서 스키마를 정의하고 유효성 검사를 제공합니다.
"""

from typing import List, Dict, Any, Optional
from datetime import datetime
from pydantic import BaseModel, Field, validator


class NewsArticleModel(BaseModel):
    """뉴스 기사 데이터 모델"""
    
    title: str
    content: str
    url: str
    press: str
    category: str
    published_at: datetime
    collected_at: datetime = Field(default_factory=datetime.now)
    keywords: Optional[List[str]] = None
    
    class Config:
        """Pydantic 설정"""
        json_encoders = {
            datetime: lambda dt: dt.isoformat()
        }
    
    @validator('url')
    def url_must_be_valid(cls, v):
        """URL 유효성 검사"""
        if not v.startswith(('http://', 'https://')):
            raise ValueError('URL은 http:// 또는 https://로 시작해야 합니다')
        return v


class ProcessedArticleModel(NewsArticleModel):
    """텍스트 처리된 뉴스 기사 모델"""
    
    processed_content: str
    processed_at: datetime = Field(default_factory=datetime.now)


class SentimentAnalysisModel(BaseModel):
    """감성 분석 결과 모델"""
    
    sentiment: str  # 'positive', 'negative', 'neutral'
    score: float
    confidence: float


class TopicAnalysisModel(BaseModel):
    """토픽 분석 결과 모델"""
    
    main_topics: List[str]
    topic_keywords: Dict[str, List[str]]
    

class SentimentArticleModel(ProcessedArticleModel):
    """감성 분석된 뉴스 기사 모델"""
    
    sentiment_analysis: Dict[str, Any] = {
        "overall_sentiment": None,
        "paragraph_sentiments": []
    }
    sentiment_processed_at: datetime = Field(default_factory=datetime.now)


class SummaryArticleModel(ProcessedArticleModel):
    """요약된 뉴스 기사 모델"""
    
    summary: str
    summary_processed_at: datetime = Field(default_factory=datetime.now)


# MongoDB 문서를 Pydantic 모델로 변환
def doc_to_model(document: Dict[str, Any], model_class) -> BaseModel:
    """MongoDB 문서를 Pydantic 모델로 변환
    
    Args:
        document: MongoDB 문서
        model_class: 변환할 Pydantic 모델 클래스
        
    Returns:
        BaseModel: Pydantic 모델 인스턴스
    """
    # ObjectId를 문자열로 변환
    if '_id' in document:
        document['_id'] = str(document['_id'])
    
    # datetime 문자열을 datetime 객체로 변환
    for key, value in document.items():
        if isinstance(value, str) and key.endswith('_at'):
            try:
                document[key] = datetime.fromisoformat(value)
            except ValueError:
                pass
    
    return model_class(**document)


# Pydantic 모델을 MongoDB 문서로 변환
def model_to_doc(model: BaseModel) -> Dict[str, Any]:
    """Pydantic 모델을 MongoDB 문서로 변환
    
    Args:
        model: Pydantic 모델 인스턴스
        
    Returns:
        Dict: MongoDB 문서 형식
    """
    # 모델을 사전으로 변환
    doc = model.dict()
    
    # _id 필드 제거 (MongoDB가 자동으로 생성)
    if '_id' in doc:
        del doc['_id']
    
    return doc 