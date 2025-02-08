import json
import urllib.request
import urllib.parse
from datetime import datetime
from typing import List, Optional
import time
from tenacity import retry, stop_after_attempt, wait_exponential

from ..utils.config import NaverNewsConfig
from ..utils.models import NewsArticle

class NaverNewsAPICollector:
    def __init__(self):
        self.client_id = NaverNewsConfig.NAVER_CLIENT_ID
        self.client_secret = NaverNewsConfig.NAVER_CLIENT_SECRET
        
        if not self.client_id or not self.client_secret:
            raise ValueError("NAVER_CLIENT_ID and NAVER_CLIENT_SECRET must be set in .env file")
    
    @retry(stop=stop_after_attempt(NaverNewsConfig.MAX_RETRIES),
           wait=wait_exponential(multiplier=NaverNewsConfig.RETRY_DELAY))
    def search_news(self, query: str, display: int = 100, start: int = 1) -> List[NewsArticle]:
        encoded_query = urllib.parse.quote(query)
        url = f"https://openapi.naver.com/v1/search/news?query={encoded_query}&display={display}&start={start}"
        
        request = urllib.request.Request(url)
        request.add_header("X-Naver-Client-Id", self.client_id)
        request.add_header("X-Naver-Client-Secret", self.client_secret)
        
        with urllib.request.urlopen(request) as response:
            if response.getcode() == 200:
                result = json.loads(response.read().decode('utf-8'))
                return self._parse_response(result, query)
            else:
                raise Exception(f"API request failed with status code: {response.getcode()}")
    
    def collect_by_category(self, category: str, max_items: int = 100) -> List[NewsArticle]:
        category_code = NaverNewsConfig.get_category_code(category)
        articles = []
        
        start = 1
        while len(articles) < max_items:
            try:
                new_articles = self.search_news(f"news_office_{category_code}", display=100, start=start)
                if not new_articles:
                    break
                    
                articles.extend(new_articles)
                start += 100
                time.sleep(NaverNewsConfig.REQUEST_DELAY)
            except Exception as e:
                print(f"Error collecting news for category {category}: {str(e)}")
                break
        
        return articles[:max_items]
    
    def _parse_response(self, response: dict, category: str) -> List[NewsArticle]:
        articles = []
        
        for item in response.get('items', []):
            try:
                # HTML 태그 제거
                title = self._clean_text(item.get('title', ''))
                description = self._clean_text(item.get('description', ''))
                
                article = NewsArticle(
                    title=title,
                    content=description,
                    url=item.get('link', ''),
                    press=item.get('publisher', ''),
                    category=category,
                    published_at=datetime.strptime(item.get('pubDate'), '%a, %d %b %Y %H:%M:%S +0900'),
                    keywords=None  # API에서는 키워드를 제공하지 않음
                )
                articles.append(article)
            except Exception as e:
                print(f"Error parsing article: {str(e)}")
                continue
        
        return articles
    
    @staticmethod
    def _clean_text(text: str) -> str:
        """HTML 태그와 특수문자 제거"""
        import re
        text = re.sub('<[^<]+?>', '', text)  # Remove HTML tags
        text = re.sub('&[a-zA-Z]+;', '', text)  # Remove HTML entities
        return text.strip() 