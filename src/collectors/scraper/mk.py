from typing import Dict, List, Optional
import asyncio
import aiohttp
from bs4 import BeautifulSoup
from datetime import datetime

from .base import BaseScraper, logger
from ..utils.models import NewsArticle

class MKScraper(BaseScraper):
    """매일경제 일반 뉴스 스크래퍼
    
    매일경제 뉴스 웹사이트에서 카테고리별 최신 일반 뉴스를 수집합니다.
    """
    
    def __init__(self, kafka_bootstrap_servers: str):
        super().__init__("mk", kafka_bootstrap_servers)
        
        self.categories = {
            'economy': ['economy', 'stock', 'realestate'],  # 경제/증권/부동산 통합
            'business': 'business',      # 기업
            'politics': 'politics',      # 정치
            'society': 'society',        # 사회
            'world': 'world',           # 국제
            'culture': 'culture',        # 문화
            'it': 'it',                  # IT
        }
        self.base_url = "https://www.mk.co.kr/news"
    
    async def get_news_content(self, session: aiohttp.ClientSession, url: str, category: str) -> Optional[NewsArticle]:
        """뉴스 기사의 내용을 수집"""
        try:
            async with session.get(url) as response:
                if response.status != 200:
                    logger.error(f"Failed to fetch {url}: Status {response.status}")
                    return None
                
                html = await response.text()
                soup = BeautifulSoup(html, 'html.parser')
                
                # 제목 추출
                title = self._extract_title(soup)
                if not title:
                    logger.warning(f"제목을 찾을 수 없음: {url}")
                    return None
                
                # 본문 추출
                content = self._extract_content(soup)
                if not content:
                    logger.warning(f"본문을 찾을 수 없음: {url}")
                    return None
                
                # 발행일 추출
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
    
    def _extract_title(self, soup: BeautifulSoup) -> Optional[str]:
        """제목 추출"""
        for title_selector in ['h1.top_title', '.article_title', 'h2.news_ttl', 'h3.news_ttl']:
            if title_elem := soup.select_one(title_selector):
                return title_elem.text.strip()
        return None
    
    def _extract_content(self, soup: BeautifulSoup) -> Optional[str]:
        """본문 추출"""
        if content_elem := soup.select_one('div.news_cnt_detail_wrap'):
            # 불필요한 요소 제거
            for tag in content_elem.select('script, style, iframe, .article_footer, .reporter_area'):
                tag.decompose()
            return content_elem.text.strip()
        return None
    
    def _extract_date(self, soup: BeautifulSoup) -> datetime:
        """발행일 추출"""
        if date_elem := soup.select_one('.time'):
            try:
                date_text = date_elem.text.strip()
                if ' : ' in date_text:
                    date_text = date_text.split(' : ')[1].strip()
                return datetime.strptime(date_text, '%Y.%m.%d %H:%M')
            except Exception as e:
                logger.warning(f"발행일 파싱 실패: {str(e)}")
        return datetime.now()
    
    async def get_category_news(self, category: str) -> List[NewsArticle]:
        """특정 카테고리의 최신 뉴스 목록을 수집"""
        news_list: List[NewsArticle] = []
        
        try:
            async with aiohttp.ClientSession(headers=self.headers) as session:
                # 카테고리에 매핑된 URL 목록 가져오기
                url_categories = self.categories.get(category)
                if not url_categories:
                    logger.error(f"알 수 없는 카테고리: {category}")
                    return []
                
                # 리스트인 경우 (economy) 여러 URL에서 수집
                if isinstance(url_categories, list):
                    for url_category in url_categories:
                        url = f"{self.base_url}/{url_category}/"
                        logger.info(f"수집 URL: {url} (카테고리: {category})")
                        
                        async with session.get(url) as response:
                            if response.status != 200:
                                logger.error(f"Failed to fetch URL category {url_category}")
                                continue
                            
                            news_links = await self._extract_news_links(response)
                            if news_links:
                                # 모든 뉴스를 economy 카테고리로 저장
                                tasks = [
                                    asyncio.create_task(self.get_news_content(session, link, 'economy'))
                                    for link in news_links
                                ]
                                
                                results = await asyncio.gather(*tasks)
                                sub_news_list = [article for article in results if article is not None]
                                news_list.extend(sub_news_list)
                                logger.info(f"{url_category} URL에서 {len(sub_news_list)}개 기사 수집 (economy 토픽으로 매핑)")
                else:
                    # 다른 카테고리들은 그대로 처리
                    url = f"{self.base_url}/{url_categories}/"
                    logger.info(f"수집 URL: {url}")
                    
                    async with session.get(url) as response:
                        if response.status != 200:
                            logger.error(f"Failed to fetch category {category}")
                            return []
                        
                        news_links = await self._extract_news_links(response)
                        if news_links:
                            tasks = [
                                asyncio.create_task(self.get_news_content(session, link, category))
                                for link in news_links
                            ]
                            
                            results = await asyncio.gather(*tasks)
                            news_list = [article for article in results if article is not None]
                
                logger.info(f"카테고리 {category}에서 총 {len(news_list)}개의 기사를 수집했습니다")
                return news_list[:30]  # 최대 30개 기사 반환
                
        except Exception as e:
            logger.error(f"Error processing category {category}: {str(e)}")
            return []

    async def _extract_news_links(self, response: aiohttp.ClientResponse) -> List[str]:
        """뉴스 링크 추출 헬퍼 메서드"""
        html = await response.text()
        soup = BeautifulSoup(html, 'html.parser')
        
        news_links = []
        articles = soup.select('li.news_node:not(.ad_wrap)')[:10]  # 광고 제외하고 상위 10개 선택
        
        for article in articles:
            if link_elem := article.select_one('a.news_item'):
                if link := link_elem.get('href', ''):
                    if not link.startswith('http'):
                        link = f"https://www.mk.co.kr{link}"
                    news_links.append(link)
                    if title_elem := article.select_one('h3.news_ttl'):
                        logger.info(f"발견된 링크: {title_elem.text.strip()} - {link}")
        
        return news_links

async def test_scraper():
    """스크래퍼 테스트 함수"""
    kafka_servers = "localhost:9092"
    scraper = MKScraper(kafka_servers)
    
    try:
        test_categories = ['economy']  # economy 카테고리 테스트
        
        for category in test_categories:
            logger.info(f"\n=== {category} 카테고리 테스트 시작 ===")
            articles = await scraper.get_category_news(category)
            
            logger.info(f"\n{category} 카테고리에서 {len(articles)}개의 기사를 수집했습니다.")
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