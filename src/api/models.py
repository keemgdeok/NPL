from typing import List, Dict, Optional, Any
from pydantic import BaseModel, Field
from datetime import datetime

class TopicAnalysis(BaseModel):
    topic_distribution: List[float]
    main_topics: List[int]
    topic_keywords: List[List[str]]

class SentimentScores(BaseModel):
    sentiment: str
    scores: Dict[str, float]

class SentimentAnalysis(BaseModel):
    overall_sentiment: SentimentScores
    sentiment_keywords: Dict[str, List[str]]

class NewsArticle(BaseModel):
    url: str
    title: str
    content: str
    processed_content: str
    press: str
    category: str
    published_at: datetime
    collected_at: datetime
    keywords: Optional[List[str]] = None
    topic_analysis: Optional[TopicAnalysis] = None
    sentiment_analysis: Optional[SentimentAnalysis] = None

class NewsResponse(BaseModel):
    total: int
    page: int
    size: int
    articles: List[NewsArticle]

class TopicSummary(BaseModel):
    topic_id: int
    keywords: List[str]
    article_count: int
    sentiment_distribution: Dict[str, int]

class CategorySummary(BaseModel):
    category: str
    article_count: int
    sentiment_distribution: Dict[str, int]
    top_topics: List[TopicSummary]

class StatsSummary(BaseModel):
    total_articles: int
    categories: List[CategorySummary]
    time_range: Dict[str, datetime] 

# 추가: 시간별 분석을 위한 모델
class TimePoint(BaseModel):
    """시간별 데이터 포인트"""
    timestamp: datetime
    count: int
    metadata: Optional[Dict[str, Any]] = None

class TimelineResponse(BaseModel):
    """시간별 분석 응답"""
    interval: str  # 'hour', 'day', 'week'
    data: List[TimePoint]
    category: Optional[str] = None
    sentiment: Optional[str] = None
    total: int
    time_range: Dict[str, datetime]

# 추가: 감성 분석 트렌드를 위한 모델
class SentimentTimePoint(BaseModel):
    """감성 분석 시간별 데이터 포인트"""
    timestamp: datetime
    positive: int = 0
    neutral: int = 0
    negative: int = 0
    total: int = 0

class SentimentTrendResponse(BaseModel):
    """감성 분석 트렌드 응답"""
    interval: str  # 'hour', 'day', 'week'
    data: List[SentimentTimePoint]
    category: Optional[str] = None
    total: int
    time_range: Dict[str, datetime]

# 추가: 키워드 분석을 위한 모델
class KeywordInfo(BaseModel):
    """키워드 정보"""
    keyword: str
    count: int
    score: float  # 중요도 점수 (예: TF-IDF)
    sentiment_distribution: Optional[Dict[str, int]] = None

class TrendingKeywordsResponse(BaseModel):
    """트렌딩 키워드 응답"""
    keywords: List[KeywordInfo]
    category: Optional[str] = None
    total_articles: int
    time_range: Dict[str, datetime]

# 추가: 키워드 네트워크를 위한 모델
class KeywordNode(BaseModel):
    """키워드 네트워크 노드"""
    id: str
    label: str
    size: int = 1
    score: float = 1.0

class KeywordEdge(BaseModel):
    """키워드 네트워크 엣지"""
    source: str
    target: str
    weight: float

class KeywordNetworkResponse(BaseModel):
    """키워드 네트워크 응답"""
    nodes: List[KeywordNode]
    edges: List[KeywordEdge]
    root_keyword: str
    depth: int
    time_range: Dict[str, datetime]

# 추가: 검색 요청을 위한 모델
class SearchRequest(BaseModel):
    """검색 요청"""
    query: str
    categories: Optional[List[str]] = None
    sentiments: Optional[List[str]] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    include_keywords: Optional[List[str]] = None
    exclude_keywords: Optional[List[str]] = None
    press: Optional[List[str]] = None
    page: int = Field(1, ge=1)
    size: int = Field(20, ge=1, le=100) 