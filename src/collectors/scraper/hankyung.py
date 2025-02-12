from typing import Dict, List, Optional
import asyncio
import aiohttp
from bs4 import BeautifulSoup
from datetime import datetime

from .base import BaseScraper, logger
from ..utils.models import NewsArticle

class HankyungScraper(BaseScraper):
    """한국경제 뉴스 스크래퍼
    
    한국경제 뉴스 웹사이트에서 카테고리별 최신 뉴스를 수집합니다.
    """
    
    def __init__(self, kafka_bootstrap_servers: str):
        super().__init__("hankyung", kafka_bootstrap_servers)
        
        # URL과 토픽을 한 번에 매핑
        self.categories = {
            'economy': 'economy',
            'society': 'society',
            'world': 'international',    # world 요청 시 -> international URL 사용
            'politics': 'politics',
            'it': 'it'
        }
        
        self.base_url = "https://www.hankyung.com"
    
    async def get_news_content(self, session: aiohttp.ClientSession, url: str, category: str) -> Optional[NewsArticle]:
        """뉴스 기사의 내용을 수집"""
        try:
            async with session.get(url) as response:
                if response.status != 200:
                    logger.error(f"Failed to fetch {url}: Status {response.status}")
                    return None
                
                html = await response.text()
                soup = BeautifulSoup(html, 'html.parser')
                
                # 제목과 본문 추출
                title = self._extract_title(soup)
                content = self._extract_content(soup)
                
                if not title or not content:
                    return None
                
                # 발행일 추출
                published_at = self._extract_date(soup)
                
                return NewsArticle(
                    title=title,
                    content=content,
                    url=url,
                    press="한국경제",
                    category=category,
                    published_at=published_at
                )
                
        except Exception as e:
            logger.error(f"Error processing {url}: {str(e)}")
            return None
    
    def _extract_title(self, soup: BeautifulSoup) -> Optional[str]:
        """제목 추출"""
        title_elem = soup.select_one('h1.headline')
        if not title_elem:
            logger.warning("제목을 찾을 수 없음")
            return None
        return title_elem.text.strip()
    
    def _extract_content(self, soup: BeautifulSoup) -> Optional[str]:
        """본문 추출"""
        content_elem = soup.select_one('div.article-body')
        if not content_elem:
            logger.warning("본문을 찾을 수 없음")
            return None
            
        # 불필요한 요소 제거
        for tag in content_elem.select('script, style, iframe, .article-ad'):
            tag.decompose()
        return content_elem.text.strip()
    
    def _extract_date(self, soup: BeautifulSoup) -> datetime:
        """발행일 추출"""
        date_elem = soup.select_one('span.txt-date')
        if date_elem:
            try:
                date_text = date_elem.text.strip()
                return datetime.strptime(date_text, '%Y.%m.%d %H:%M')
            except Exception as e:
                logger.warning(f"발행일 파싱 실패: {str(e)}")
        return datetime.now()
    
    async def get_category_news(self, category: str) -> List[NewsArticle]:
        """특정 카테고리의 뉴스 목록을 수집"""
        try:
            async with aiohttp.ClientSession(headers=self.headers) as session:
                # URL 카테고리 가져오기 (international)
                url_category = self.categories[category]
                url = f"{self.base_url}/{url_category}"
                
                logger.info(f"수집 시작: {url} (요청 카테고리: {category})")
                
                # 뉴스 목록 페이지 수집
                news_links = await self._get_news_links(session, url)
                if not news_links:
                    return []
                
                # 개별 뉴스 기사 수집 (원래 요청된 카테고리로 저장)
                tasks = [
                    self.get_news_content(session, link, category)  # category 사용 (world)
                    for link in news_links
                ]
                results = await asyncio.gather(*tasks)
                
                news_list = [article for article in results if article is not None]
                logger.info(f"수집 완료: {len(news_list)}개 기사")
                
                return news_list
                
        except Exception as e:
            logger.error(f"Error processing category {category}: {str(e)}")
            return []
    
    async def _get_news_links(self, session: aiohttp.ClientSession, url: str) -> List[str]:
        """뉴스 링크 목록 추출"""
        async with session.get(url) as response:
            if response.status != 200:
                logger.error(f"Failed to fetch URL: {url}")
                return []
            
            html = await response.text()
            soup = BeautifulSoup(html, 'html.parser')
            
            news_links = []
            for item in soup.select('ul.news-list > li')[:20]:
                if title_elem := item.select_one('h3.news-tit a'):
                    if link := title_elem.get('href', ''):
                        if link.startswith('http'):
                            news_links.append(link)
                            logger.info(f"발견된 기사: {title_elem.text.strip()}")
            
            if not news_links:
                logger.warning("뉴스 링크를 찾을 수 없습니다")
            
            return news_links

async def test_scraper():
    """스크래퍼 테스트"""
    scraper = HankyungScraper("localhost:9092")
    
    try:
        for category in ['world']:  # 테스트할 카테고리
            logger.info(f"\n=== {category} 카테고리 테스트 시작 ===")
            articles = await scraper.get_category_news(category)
            
            for article in articles:
                logger.info(f"제목: {article.title}")
                logger.info(f"카테고리: {article.category}")
                logger.info("---")
    except Exception as e:
        logger.error(f"테스트 중 오류 발생: {str(e)}")
    finally:
        scraper.close()

if __name__ == "__main__":
    asyncio.run(test_scraper()) 