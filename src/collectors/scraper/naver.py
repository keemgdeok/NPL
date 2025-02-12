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
            'culture': '103',       # 생활/문화
        }
        self.base_url = "https://news.naver.com/section"
    
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
                title = None
                title_elem = soup.select_one('#title_area')
                if title_elem:
                    title = title_elem.text.strip()
                
                if not title:
                    logger.warning(f"제목을 찾을 수 없음: {url}")
                    return None
                
                # 본문 추출
                content = None
                content_elem = soup.select_one('#newsct_article')
                if content_elem:
                    # 불필요한 요소 제거
                    for tag in content_elem.select('script, style, iframe, .media_end_head'):
                        tag.decompose()
                    content = content_elem.text.strip()
                
                if not content:
                    logger.warning(f"본문을 찾을 수 없음: {url}")
                    return None
                
                # 발행일 추출
                published_at = datetime.now()  # 기본값
                date_elem = soup.select_one('.media_end_head_info_datestamp')
                if date_elem:
                    try:
                        date_text = date_elem.text.strip()
                        published_at = datetime.strptime(date_text, '%Y.%m.%d. %H:%M')
                    except Exception as e:
                        logger.warning(f"발행일 파싱 실패: {str(e)}")
                
                # 언론사 추출
                press = "네이버뉴스"
                press_elem = soup.select_one('.media_end_head_top a img')
                if press_elem:
                    press = press_elem.get('title', '네이버뉴스')
                
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
    
    async def get_category_news(self, category: str) -> List[NewsArticle]:
        """특정 카테고리의 인기 뉴스 목록을 수집"""
        news_list: List[NewsArticle] = []
        
        try:
            async with aiohttp.ClientSession(headers=self.headers) as session:
                # economy 카테고리의 경우 여러 서브 카테고리 수집
                if category == 'economy' and isinstance(self.categories[category], list):
                    for sub_category in self.categories[category]:
                        url = f"{self.base_url}/{sub_category}/"
                        logger.info(f"수집 URL: {url}")
                        
                        async with session.get(url) as response:
                            if response.status != 200:
                                logger.error(f"Failed to fetch category {sub_category}")
                                continue
                            
                            html = await response.text()
                            soup = BeautifulSoup(html, 'html.parser')
                            
                            # 인기 뉴스 링크 추출 (상위 10개)
                            news_links = []
                            rank_items = soup.select('h3.news_ttl')[:10]
                            
                            for item in rank_items:
                                link_elem = item.find_parent('a')
                                if link_elem:
                                    link = link_elem.get('href', '')
                                    title = item.text.strip()
                                    if link and link.startswith('http'):
                                        news_links.append(link)
                                        logger.info(f"발견된 링크: {title} - {link}")
                            
                            if news_links:
                                # 비동기로 뉴스 내용 수집 (economy 카테고리로 통일)
                                tasks = [
                                    asyncio.create_task(self.get_news_content(session, link, 'economy'))
                                    for link in news_links
                                ]
                                
                                results = await asyncio.gather(*tasks)
                                sub_news_list = [article for article in results if article is not None]
                                news_list.extend(sub_news_list)
                                
                                logger.info(f"서브카테고리 {sub_category}에서 {len(sub_news_list)}개의 기사를 수집했습니다")
                else:
                    # 단일 카테고리 처리 (기존 코드)
                    url = f"{self.base_url}/{self.categories[category]}/"
                    logger.info(f"수집 URL: {url}")
                    
                    async with session.get(url) as response:
                        if response.status != 200:
                            logger.error(f"Failed to fetch category {category}")
                            return []
                        
                        html = await response.text()
                        soup = BeautifulSoup(html, 'html.parser')
                        
                        news_links = []
                        rank_items = soup.select('h3.news_ttl')[:10]
                        
                        for item in rank_items:
                            link_elem = item.find_parent('a')
                            if link_elem:
                                link = link_elem.get('href', '')
                                title = item.text.strip()
                                if link and link.startswith('http'):
                                    news_links.append(link)
                                    logger.info(f"발견된 링크: {title} - {link}")
                        
                        if news_links:
                            tasks = [
                                asyncio.create_task(self.get_news_content(session, link, category))
                                for link in news_links
                            ]
                            
                            results = await asyncio.gather(*tasks)
                            news_list = [article for article in results if article is not None]
                
                logger.info(f"카테고리 {category}에서 총 {len(news_list)}개의 기사를 수집했습니다")
                return news_list[:20]  # 최대 20개 기사만 반환
                
        except Exception as e:
            logger.error(f"Error processing category {category}: {str(e)}")
            return []

async def test_scraper():
    """스크래퍼 테스트 함수"""
    # Kafka 서버 주소 설정
    kafka_servers = "localhost:9092"
    
    # 스크래퍼 인스턴스 생성
    scraper = NaverScraper(kafka_servers)
    
    try:
        # 테스트할 카테고리 선택
        test_categories = ['economy']
        
        for category in test_categories:
            logger.info(f"\n=== {category} 카테고리 테스트 시작 ===")
            articles = await scraper.get_category_news(category)
            
            # 결과 출력
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