from typing import Dict, List, Optional
import asyncio
import aiohttp
from bs4 import BeautifulSoup
from datetime import datetime

from .base import BaseScraper, logger
from ..utils.models import NewsArticle

class NaverScraper(BaseScraper):
    """네이버 뉴스 스크래퍼
    
    네이버 뉴스 웹사이트에서 카테고리별 최신 뉴스를 수집합니다.
    """
    
    def __init__(self, kafka_bootstrap_servers: str):
        super().__init__("naver", kafka_bootstrap_servers)
        
        self.categories = {
            'economy': '101',      # 경제
            'it': '105',          # IT/과학
            'society': '102',      # 사회
            'politics': '100',     # 정치
            'world': '104',        # 세계
            'culture': '103',      # 생활/문화
        }
        self.base_url = "https://news.naver.com/section"
    
    def _extract_title(self, soup: BeautifulSoup) -> Optional[str]:
        """제목 추출
        
        Args:
            soup (BeautifulSoup): 파싱된 HTML
            
        Returns:
            Optional[str]: 추출된 제목 또는 None
        """
        title_elem = soup.select_one('#title_area')
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
        content_elem = soup.select_one('#newsct_article')
        if not content_elem:
            logger.warning("본문을 찾을 수 없음")
            return None
            
        # 불필요한 요소 제거
        for tag in content_elem.select('script, style, iframe, .media_end_head'):
            tag.decompose()
        return content_elem.text.strip()
    
    def _extract_press(self, soup: BeautifulSoup) -> str:
        """언론사 추출
        
        Args:
            soup (BeautifulSoup): 파싱된 HTML
            
        Returns:
            str: 추출된 언론사 이름
        """
        press_elem = soup.select_one('.media_end_head_top a img')
        return press_elem.get('title', '네이버뉴스') if press_elem else '네이버뉴스'
    
    def _extract_date(self, soup: BeautifulSoup) -> datetime:
        """발행일 추출
        
        Args:
            soup (BeautifulSoup): 파싱된 HTML
            
        Returns:
            datetime: 추출된 발행일시
        """
        try:
            # 정확한 선택자를 사용하여 날짜 요소 찾기
            date_elem = soup.select_one('.media_end_head_info_datestamp_time, ._ARTICLE_DATE_TIME')
            
            # data-date-time 속성에서 날짜 추출
            if date_elem and date_elem.has_attr('data-date-time'):
                date_text = date_elem['data-date-time']
                return datetime.strptime(date_text, '%Y-%m-%d %H:%M:%S')
                
        except Exception as e:
            logger.warning(f"발행일 파싱 실패: {str(e)}")
            
        # 날짜를 찾지 못한 경우 현재 시간 반환
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
                
                press = self._extract_press(soup)
                published_at = self._extract_date(soup)
                
                return NewsArticle(
                    title=title,
                    content=content,
                    url=url,
                    press=press,
                    category=category,
                    published_at=published_at
                )
                
        except Exception as e:
            logger.error(f"Error processing {url}: {str(e)}")
            return None
    
    async def _extract_news_links(self, response: aiohttp.ClientResponse) -> List[str]:
        """뉴스 링크 추출"""
        html = await response.text()
        soup = BeautifulSoup(html, 'html.parser')
        news_links = []
        
        try:
            # 헤드라인 뉴스 섹션에서 링크 추출
            news_items = soup.select('.sa_text_title')
            
            for item in news_items[:30]:  # 최대 30개 링크 수집
                if link := item.get('href', ''):
                    if link.startswith('http'):
                        news_links.append(link)
                        if title_elem := item.select_one('strong.sa_text_strong'):
                            logger.info(f"발견된 기사: {title_elem.text.strip()}")
            
            if not news_links:
                logger.warning("뉴스 링크를 찾을 수 없음")
                logger.debug(f"현재 HTML 구조: {soup.select('.section_article')}")
            
        except Exception as e:
            logger.error(f"링크 추출 중 오류 발생: {str(e)}")
        
        return news_links
    
    async def get_category_news(self, category: str) -> List[NewsArticle]:
        """특정 카테고리의 뉴스 목록을 수집"""
        try:
            async with aiohttp.ClientSession(headers=self.headers) as session:
                url = f"{self.base_url}/{self.categories[category]}"
                logger.info(f"수집 URL: {url}")
                
                async with self.semaphore:
                    async with session.get(url) as response:
                        if response.status != 200:
                            logger.error(f"Failed to fetch category {category}: {response.status}")
                            return []
                        
                        news_links = await self._extract_news_links(response)
                        if not news_links:
                            return []
                        
                        # 병렬로 뉴스 기사 수집
                        tasks = [
                            asyncio.create_task(self.get_news_content(session, link, category))
                            for link in news_links
                        ]
                        
                        results = await asyncio.gather(*tasks)
                        news_list = [article for article in results if article is not None]
                        
                        logger.info(f"카테고리 {category}에서 총 {len(news_list)}개의 기사를 수집했습니다")
                        return news_list[:30]
                
        except Exception as e:
            logger.error(f"Error processing category {category}: {str(e)}")
            return []

async def test_scraper():
    """스크래퍼 테스트 함수"""
    scraper = NaverScraper("localhost:9092")
    
    try:
        for category in ['politics']:  # 테스트할 카테고리
            logger.info(f"\n=== {category} 카테고리 테스트 시작 ===")
            articles = await scraper.get_category_news(category)
            
            for idx, article in enumerate(articles, 1):
                logger.info(f"\n{idx}. {article.title}")
                logger.info(f"URL: {article.url}")
                logger.info(f"언론사: {article.press}")
                logger.info(f"발행일: {article.published_at}")
                logger.info(f"본문 미리보기: {article.content[:100]}...")
            
            logger.info(f"\n=== {category} 카테고리 테스트 완료 ===\n")
            
    except Exception as e:
        logger.error(f"테스트 중 오류 발생: {str(e)}")
    finally:
        scraper.close()

if __name__ == "__main__":
    asyncio.run(test_scraper())