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

class MKNewsTestScraper:
    """매일경제 뉴스 스크래퍼 테스트를 위한 클래스.
    
    이 클래스는 매일경제 뉴스 웹사이트에서 카테고리별 많이 본 뉴스를 수집하고
    결과를 검증하는 기능을 제공합니다.
    
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
            'economy': 'economy',
            'business': 'business',
            'society': 'society',
            'world': 'world',
            'realestate': 'realestate',
            'stock': 'stock',
            'politics': 'politics',
            'it': 'it',
            'culture': 'culture'
        }
        self.results_dir: Path = Path('test_results')
        self.results_dir.mkdir(exist_ok=True)
        self.base_url: str = "https://www.mk.co.kr/news"
        
        # 동시 처리할 카테고리 수 제한
        self.semaphore = asyncio.Semaphore(5)  # 5개씩 병렬 처리
    
    async def get_news_content(self, session: aiohttp.ClientSession, url: str) -> Optional[Dict[str, str]]:
        """뉴스 기사의 내용을 비동기적으로 수집
        
        Args:
            session (aiohttp.ClientSession): 비동기 HTTP 세션
            url (str): 수집할 뉴스 기사의 URL
            
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
                title = soup.select_one('.top_title')
                title = title.text.strip() if title else "제목 없음"
                
                # 본문 추출
                content = soup.select_one('div.news_cnt_detail_wrap')
                content = content.text.strip() if content else "본문 없음"
                
                return {
                    'title': title,
                    'content': content,
                    'url': url,
                    'collected_at': datetime.now().isoformat()
                }
                
        except Exception as e:
            logger.error(f"Error processing {url}: {str(e)}")
            return None
    
    async def get_category_news(self, category: str) -> List[Dict[str, str]]:
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
                    
                    # 뉴스 링크 추출 (광고 제외)
                    news_links = []
                    articles = soup.select('li.news_node:not(.ad_wrap)')[:10]  # 광고 제외하고 상위 10개 선택
                    
                    for article in articles:
                        link_elem = article.select_one('a.news_item')
                        title_elem = article.select_one('h3.news_ttl')
                        
                        if link_elem and title_elem:
                            link = link_elem.get('href', '')
                            title = title_elem.text.strip()
                            if link:
                                news_links.append(link)
                                logger.info(f"발견된 링크: {title} - {link}")
                    
                    if not news_links:
                        logger.warning(f"카테고리 {category}에서 뉴스 링크를 찾을 수 없습니다")
                        return []
                    
                    # 비동기로 뉴스 내용 수집
                    tasks = [
                        self.get_news_content(session, link)
                        for link in news_links
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
        """수집 결과를 파일로 저장
        
        Args:
            category (str): 뉴스 카테고리
            news_data (List[Dict[str, str]]): 저장할 뉴스 데이터
        """
        result_file = self.results_dir / f"mk_{category}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        
        with open(result_file, 'w', encoding='utf-8') as f:
            json.dump(news_data, f, ensure_ascii=False, indent=2)

async def main() -> None:
    """메인 실행 함수"""
    scraper = MKNewsTestScraper()
    categories = list(scraper.categories.keys())
    
    async def process_category(category: str) -> None:
        async with scraper.semaphore:  # 세마포어로 5개씩 제한
            logger.info(f"=== 카테고리 {category} 뉴스 수집 시작 ===")
            news_list = await scraper.get_category_news(category)
            
            logger.info(f"수집된 뉴스 개수: {len(news_list)}")
            for idx, news in enumerate(news_list, 1):
                logger.info(f"\n{idx}. {news['title']}")
                logger.info(f"URL: {news['url']}")
                logger.info(f"본문 일부: {news['content'][:100]}...")
            
            logger.info(f"=== 카테고리 {category} 뉴스 수집 완료 ===\n")
    
    # 모든 카테고리를 동시에 처리 (세마포어로 5개씩 제한)
    tasks = [process_category(category) for category in categories]
    await asyncio.gather(*tasks)

if __name__ == "__main__":
    asyncio.run(main()) 