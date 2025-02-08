from typing import List, Dict, Optional
from pydantic import BaseModel
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