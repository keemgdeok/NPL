from typing import Dict, List, Optional, Any
import asyncio
import aiohttp
from bs4 import BeautifulSoup
import time
from datetime import datetime
import logging
from pathlib import Path
import json

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class MKPopularNewsScraper:
    """매일경제 많이 본 뉴스 
    
    이 클래스는 매일경제 뉴스 웹사이트에서 카테고리별 많이 본 뉴스를 수집
    
    Attributes:
        headers (Dict[str, str]): HTTP 요청에 사용될 헤더
        categories (Dict[str, str]): 뉴스 카테고리 매핑
        results_dir (Path): 결과 저장 디렉토리
    """
    
    def __init__(self) -> None:
        self.headers: Dict[str, str] = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        self.categories: Dict[str, str] = {
            'economy': '경제',
            'business': '기업',
            'society': '사회',
            'world': '국제',
            'realestate': '부동산',
            'stock': '증권',
            'politics': '정치',
            'it': 'IT·과학',
            'culture': '문화'
        }
        self.results_dir: Path = Path('test_results')
        self.results_dir.mkdir(exist_ok=True)
        self.base_url: str = "https://www.mk.co.kr/news/ranking"
        
        # 동시 처리할 카테고리 수 제한
        self.semaphore = asyncio.Semaphore(5)  # 5개씩 병렬 처리
    
    async def get_news_content(self, session: aiohttp.ClientSession, url: str, category: str) -> Optional[Dict[str, str]]:
        """뉴스 기사의 내용을 비동기적으로 수집
        
        Args:
            session (aiohttp.ClientSession): 비동기 HTTP 세션
            url (str): 수집할 뉴스 기사의 URL
            category (str): 뉴스 카테고리
            
        Returns:
            Optional[Dict[str, str]]: 뉴스 기사 정보 (제목, 내용, URL) 또는 None (오류 발생시)
        """
        try:
            async with session.get(url) as response:
                if response.status != 200:
                    logger.error(f"Failed to fetch {url}: Status {response.status}")
                    return None
                
                html = await response.text()
                soup = BeautifulSoup(html, 'html.parser')
                
                # 제목 추출
                title = None
                title_elem = soup.select_one('h2.news_ttl, h1.top_title')
                if title_elem:
                    title = title_elem.text.strip()
                
                if not title:
                    logger.warning(f"제목을 찾을 수 없음: {url}")
                    return None
                
                # 본문 추출
                content = None
                content_elem = soup.select_one('div.news_cnt_detail_wrap, div.article_body')
                if content_elem:
                    # 불필요한 요소 제거
                    for tag in content_elem.select('script, style, iframe, .reporter_area, .link_news'):
                        tag.decompose()
                    content = content_elem.text.strip()
                
                if not content:
                    logger.warning(f"본문을 찾을 수 없음: {url}")
                    return None
                
                return {
                    'title': title,
                    'content': content,
                    'url': url,
                    'category': category,
                    'category_name': self.categories.get(category, '기타'),
                    'collected_at': datetime.now().isoformat()
                }
                
        except Exception as e:
            logger.error(f"Error processing {url}: {str(e)}")
            return None
    
    async def get_popular_news(self, category: str) -> List[Dict[str, str]]:
        """특정 카테고리의 많이 본 뉴스 목록을 수집
        
        Args:
            category (str): 수집할 뉴스 카테고리
            
        Returns:
            List[Dict[str, str]]: 수집된 뉴스 기사 목록
        """
        news_data: List[Dict[str, str]] = []
        
        try:
            async with aiohttp.ClientSession(headers=self.headers) as session:
                # 카테고리 페이지 수집
                url = f"{self.base_url}/{category}/"
                logger.info(f"수집 URL: {url}")
                
                async with session.get(url) as response:
                    if response.status != 200:
                        logger.error(f"Failed to fetch category {category}")
                        return []
                    
                    html = await response.text()
                    soup = BeautifulSoup(html, 'html.parser')
                    
                    # 인기 뉴스 링크 추출 (상위 10개)
                    news_links = []
                    rank_items = soup.select('h3.news_ttl')[:10]  # 상위 10개만 선택
                    
                    for item in rank_items:
                        link_elem = item.find_parent('a')
                        if link_elem:
                            link = link_elem.get('href', '')
                            title = item.text.strip()
                            if link and link.startswith('http'):
                                news_links.append((link, title))
                                logger.info(f"발견된 링크: {title} - {link}")
                    
                    if not news_links:
                        logger.warning(f"인기 뉴스 링크를 찾을 수 없음: {category}")
                        return []
                    
                    # 비동기로 뉴스 내용 수집
                    tasks = [
                        self.get_news_content(session, link, category)
                        for link, _ in news_links
                    ]
                    results = await asyncio.gather(*tasks)
                    news_data = [result for result in results if result is not None]
                    
                    # 결과 저장
                    self._save_results(category, news_data)
                    
                    return news_data
                    
        except Exception as e:
            logger.error(f"Error processing category {category}: {str(e)}")
            return []
    
    def _save_results(self, category: str, news_data: List[Dict[str, str]]) -> None:
        """수집 결과를 파일로 저장합니다.
        
        Args:
            category (str): 뉴스 카테고리
            news_data (List[Dict[str, str]]): 저장할 뉴스 데이터
        """
        result_file = self.results_dir / f"mk_popular_{category}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        
        with open(result_file, 'w', encoding='utf-8') as f:
            json.dump(news_data, f, ensure_ascii=False, indent=2)

async def main() -> None:
    """메인 실행 함수"""
    scraper = MKPopularNewsScraper()
    categories = list(scraper.categories.keys())
    
    async def process_category(category: str) -> None:
        async with scraper.semaphore:  # 세마포어로 5개씩 제한
            logger.info(f"=== 카테고리 {category} 인기 뉴스 수집 시작 ===")
            news_list = await scraper.get_popular_news(category)
            
            logger.info(f"수집된 뉴스 개수: {len(news_list)}")
            for idx, news in enumerate(news_list, 1):
                logger.info(f"\n{idx}. {news['title']}")
                logger.info(f"URL: {news['url']}")
                logger.info(f"카테고리: {news['category_name']}")
                logger.info(f"본문 일부: {news['content'][:100]}...")
            
            logger.info(f"=== 카테고리 {category} 인기 뉴스 수집 완료 ===\n")
    
    # 모든 카테고리를 동시에 처리 (세마포어로 5개씩 제한)
    tasks = [process_category(category) for category in categories]
    await asyncio.gather(*tasks)

if __name__ == "__main__":
    asyncio.run(main()) 