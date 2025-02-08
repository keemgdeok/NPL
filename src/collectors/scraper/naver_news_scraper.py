from typing import Dict, List, Optional, Any
import asyncio
import aiohttp
from bs4 import BeautifulSoup
import time
from datetime import datetime
import logging
from pathlib import Path

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class NaverNewsTestScraper:
    """네이버 뉴스 스크래퍼 
    
    Attributes:
        headers (Dict[str, str]): HTTP 요청에 사용될 헤더
        session (aiohttp.ClientSession): 비동기 HTTP 세션
    """
    
    def __init__(self) -> None:
        self.headers: Dict[str, str] = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        self.results_dir: Path = Path('test_results')
        self.results_dir.mkdir(exist_ok=True)
        
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
                title = soup.select_one('#title_area')
                title = title.text.strip() if title else "제목 없음"
                
                # 본문 추출
                content = soup.select_one('#newsct_article')
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
    
    async def get_category_news(self, category_id: int) -> List[Dict[str, str]]:
        """특정 카테고리의 뉴스 목록을 수집
        
        Args:
            category_id (int): 수집할 뉴스 카테고리 ID
            
        Returns:
            List[Dict[str, str]]: 수집된 뉴스 기사 목록
        """
        base_url = f"https://news.naver.com/section/{category_id}"
        news_data: List[Dict[str, str]] = []
        
        try:
            async with aiohttp.ClientSession(headers=self.headers) as session:
                # 카테고리 페이지 수집
                async with session.get(base_url) as response:
                    if response.status != 200:
                        logger.error(f"Failed to fetch category {category_id}")
                        return []
                    
                    html = await response.text()
                    soup = BeautifulSoup(html, 'html.parser')
                    
                    # 헤드라인 뉴스 링크 추출
                    articles = soup.select('.sa_text_title')
                    news_links = []
                    
                    for article in articles[:10]:  # 상위 10개만 추출
                        link = article.get('href')
                        if link:
                            if not link.startswith('http'):
                                link = 'https://news.naver.com' + link
                            news_links.append(link)
                    
                    # 비동기로 뉴스 내용 수집
                    tasks = [
                        self.get_news_content(session, link)
                        for link in news_links
                    ]
                    results = await asyncio.gather(*tasks)
                    news_data = [result for result in results if result is not None]
                    
                    # 결과 저장
                    self._save_results(category_id, news_data)
                    
                    return news_data
                    
        except Exception as e:
            logger.error(f"Error processing category {category_id}: {str(e)}")
            return []
    
    def _save_results(self, category_id: int, news_data: List[Dict[str, str]]) -> None:
        """수집 결과를 파일로 저장
        
        Args:
            category_id (int): 뉴스 카테고리 ID
            news_data (List[Dict[str, str]]): 저장할 뉴스 데이터
        """
        import json
        result_file = self.results_dir / f"category_{category_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        
        with open(result_file, 'w', encoding='utf-8') as f:
            json.dump(news_data, f, ensure_ascii=False, indent=2)

async def main() -> None:
    """메인 실행 함수"""
    scraper = NaverNewsTestScraper()
    categories = range(100, 106)  # 100부터 105까지
    
    async def process_category(category: int) -> None:
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