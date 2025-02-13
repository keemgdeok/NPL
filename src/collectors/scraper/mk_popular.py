from typing import Dict, List, Optional
import asyncio
import aiohttp
from bs4 import BeautifulSoup
from datetime import datetime

from .base import BaseScraper, logger
from ..utils.models import NewsArticle

class MKPopularScraper(BaseScraper):
    """매일경제 인기뉴스 스크래퍼
    
    매일경제 뉴스 웹사이트에서 카테고리별 인기 뉴스를 수집합니다.
    """
    
    def __init__(self, kafka_bootstrap_servers: str):
        super().__init__("mk_popular", kafka_bootstrap_servers)
        
        self.categories = {
            'economy': ['economy', 'stock', 'realestate'],  # 경제/증권/부동산 통합
            'business': 'business',      # 기업
            'politics': 'politics',      # 정치
            'society': 'society',        # 사회
            'world': 'world',           # 국제
            'culture': 'culture',        # 문화
            'it': 'it',                  # IT
        }
        self.base_url = "https://www.mk.co.kr/news/ranking"
    
    def _extract_title(self, soup: BeautifulSoup) -> Optional[str]:
        """제목 추출
        
        Args:
            soup (BeautifulSoup): 파싱된 HTML
            
        Returns:
            Optional[str]: 추출된 제목 또는 None
        """
        title_elem = soup.select_one('h2.news_ttl, h1.top_title')
        if not title_elem:
            logger.warning("제목을 찾을 수 없음")
            return None
        return title_elem.text.strip()
    
    def _extract_content(self, soup: BeautifulSoup) -> Optional[str]:
        """본문 추출
        
        Args:
            soup (BeautifulSoup): 파싱된 HTML
            
        Returns:
            Optional[str]: 추출된 본문 또는 None
        """
        content_elem = soup.select_one('div.news_cnt_detail_wrap, div.article_body')
        if not content_elem:
            logger.warning("본문을 찾을 수 없음")
            return None
            
        # 불필요한 요소 제거
        for tag in content_elem.select('script, style, iframe, .reporter_area, .link_news'):
            tag.decompose()
        return content_elem.text.strip()
    
    def _extract_date(self, soup: BeautifulSoup) -> datetime:
        """발행일 추출
        
        Args:
            soup (BeautifulSoup): 파싱된 HTML
            
        Returns:
            datetime: 추출된 발행일시
        """
        try:
            date_elem = soup.select_one('.date')
            if date_elem:
                date_text = date_elem.text.strip()
                return datetime.strptime(date_text, '%Y.%m.%d %H:%M')
        except Exception as e:
            logger.warning(f"발행일 파싱 실패: {str(e)}")
        return datetime.now()
    
    async def get_news_content(self, session: aiohttp.ClientSession, url: str, category: str) -> Optional[NewsArticle]:
        """뉴스 기사의 내용을 수집"""
        try:
            async with session.get(url) as response:
                if response.status != 200:
                    logger.error(f"Failed to fetch {url}: Status {response.status}")
                    return None
                
                html = await response.text()
                soup = BeautifulSoup(html, 'html.parser')
                
                # 각 요소 추출
                title = self._extract_title(soup)
                content = self._extract_content(soup)
                
                if not title or not content:
                    return None
                
                published_at = self._extract_date(soup)
                
                return NewsArticle(
                    title=title,
                    content=content,
                    url=url,
                    press="매일경제",
                    category=category,
                    published_at=published_at
                )
                
        except Exception as e:
            logger.error(f"Error processing {url}: {str(e)}")
            return None
    
    async def _extract_news_links(self, response: aiohttp.ClientResponse) -> List[str]:
        """뉴스 링크 추출
        
        Args:
            response (aiohttp.ClientResponse): HTTP 응답 객체
            
        Returns:
            List[str]: 추출된 뉴스 링크 목록
        """
        html = await response.text()
        soup = BeautifulSoup(html, 'html.parser')
        news_links = []
        
        try:
            rank_items = soup.select('h3.news_ttl')[:10]  # 상위 10개 기사만 수집
            
            for item in rank_items:
                link_elem = item.find_parent('a')
                if link_elem:
                    link = link_elem.get('href', '')
                    if link and link.startswith('http'):
                        news_links.append(link)
                        logger.info(f"발견된 기사: {item.text.strip()}")
            
            if not news_links:
                logger.warning("뉴스 링크를 찾을 수 없음")
                
        except Exception as e:
            logger.error(f"링크 추출 중 오류 발생: {str(e)}")
        
        return news_links
    
    async def get_category_news(self, category: str) -> List[NewsArticle]:
        """특정 카테고리의 뉴스 목록을 수집"""
        news_list = []
        
        try:
            async with aiohttp.ClientSession(headers=self.headers) as session:
                # 카테고리 URL 목록 가져오기
                url_categories = (
                    self.categories[category]
                    if isinstance(self.categories[category], list)
                    else [self.categories[category]]
                )
                
                # 각 URL에서 뉴스 수집
                for url_category in url_categories:
                    url = f"{self.base_url}/{url_category}/"
                    logger.info(f"수집 URL: {url}")
                    
                    async with session.get(url) as response:
                        if response.status != 200:
                            logger.error(f"Failed to fetch category {category}")
                            continue
                        
                        news_links = await self._extract_news_links(response)
                        if news_links:
                            tasks = [
                                asyncio.create_task(self.get_news_content(session, link, category))
                                for link in news_links
                            ]
                            
                            results = await asyncio.gather(*tasks)
                            news_list.extend([article for article in results if article is not None])
                
                logger.info(f"카테고리 {category}에서 총 {len(news_list)}개의 기사를 수집했습니다")
                return news_list[:30]  # 최대 30개 기사 반환
                
        except Exception as e:
            logger.error(f"Error processing category {category}: {str(e)}")
            return []

async def test_scraper():
    """스크래퍼 테스트 함수"""
    scraper = MKPopularScraper("localhost:9092")
    
    try:
        for category in ['world']:  # 테스트할 카테고리
            logger.info(f"\n=== {category} 카테고리 테스트 시작 ===")
            articles = await scraper.get_category_news(category)
            
            for idx, article in enumerate(articles, 1):
                logger.info(f"\n{idx}. {article.title}")
                logger.info(f"URL: {article.url}")
                logger.info(f"발행일: {article.published_at}")
                logger.info(f"본문 미리보기: {article.content[:100]}...")
            
            logger.info(f"\n=== {category} 카테고리 테스트 완료 ===\n")
            
    except Exception as e:
        logger.error(f"테스트 중 오류 발생: {str(e)}")
    finally:
        scraper.close()

if __name__ == "__main__":
    asyncio.run(test_scraper()) 