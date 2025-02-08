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

class HankyungNewsScraper:
    """한국경제 뉴스 스크래퍼.
    
    이 클래스는 한국경제 뉴스 웹사이트에서 카테고리별 최신 뉴스를 수집합니다.
    
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
            'financial-market': 'financial',
            'industry': 'industry',
            'distribution': 'distribution',
            'society': 'society',
            'it': 'it',
            'international': 'international',
            'politics': 'politics'
        }
        self.results_dir: Path = Path('test_results')
        self.results_dir.mkdir(exist_ok=True)
        self.base_url: str = "https://www.hankyung.com"
        
        # 동시 처리할 카테고리 수 제한
        self.semaphore = asyncio.Semaphore(5)  # 5개씩 병렬 처리
    
    async def get_news_content(self, session: aiohttp.ClientSession, url: str, category: str) -> Optional[Dict[str, str]]:
        """뉴스 기사의 내용을 비동기적으로 수집합니다.
        
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
                title_elem = soup.select_one('h1.headline')
                if title_elem:
                    title = title_elem.text.strip()
                
                if not title:
                    logger.warning(f"제목을 찾을 수 없음: {url}")
                    return None
                
                # 본문 추출
                content = None
                content_elem = soup.select_one('div.article-body')
                if content_elem:
                    # 불필요한 요소 제거
                    for tag in content_elem.select('script, style, iframe, .article-ad'):
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
    
    async def get_category_news(self, category: str) -> List[Dict[str, str]]:
        """특정 카테고리의 뉴스 목록을 수집
        
        Args:
            category (str): 수집할 뉴스 카테고리
            
        Returns:
            List[Dict[str, str]]: 수집된 뉴스 기사 목록
        """
        news_data: List[Dict[str, str]] = []
        
        try:
            async with aiohttp.ClientSession(headers=self.headers) as session:
                # 카테고리 페이지 수집
                url = f"{self.base_url}/{category}"
                logger.info(f"수집 URL: {url}")
                
                async with session.get(url) as response:
                    if response.status != 200:
                        logger.error(f"Failed to fetch category {category}")
                        return []
                    
                    html = await response.text()
                    soup = BeautifulSoup(html, 'html.parser')
                    
                    # 뉴스 목록 추출
                    news_items = soup.select('ul.news-list > li')
                    news_links = []
                    
                    for item in news_items:
                        # 제목과 링크 추출
                        title_elem = item.select_one('h3.news-tit a')
                        if title_elem:
                            title = title_elem.text.strip()
                            link = title_elem.get('href', '')
                            
                            # 본문 미리보기 추출
                            preview = item.select_one('p.lead')
                            preview_text = preview.text.strip() if preview else ""
                            
                            # 날짜 추출
                            date_elem = item.select_one('span.txt-date')
                            date_text = date_elem.text.strip() if date_elem else ""
                            
                            if link and link.startswith('http'):
                                news_links.append({
                                    'title': title,
                                    'link': link,
                                    'preview': preview_text,
                                    'date': date_text
                                })
                                logger.info(f"발견된 링크: {title} - {link}")
                    
                    if not news_links:
                        logger.warning(f"뉴스 링크를 찾을 수 없음: {category}")
                        return []
                    
                    # 비동기로 뉴스 내용 수집
                    tasks = [
                        self.get_news_content(session, item['link'], category)
                        for item in news_links
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
        result_file = self.results_dir / f"hankyung_{category}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        
        with open(result_file, 'w', encoding='utf-8') as f:
            json.dump(news_data, f, ensure_ascii=False, indent=2)

async def main() -> None:
    """메인 실행 함수"""
    scraper = HankyungNewsScraper()
    categories = list(scraper.categories.keys())
    
    async def process_category(category: str) -> None:
        async with scraper.semaphore:  # 세마포어로 5개씩 제한
            logger.info(f"=== 카테고리 {category} 최신 뉴스 수집 시작 ===")
            news_list = await scraper.get_category_news(category)
            
            logger.info(f"수집된 뉴스 개수: {len(news_list)}")
            for idx, news in enumerate(news_list, 1):
                logger.info(f"\n{idx}. {news['title']}")
                logger.info(f"URL: {news['url']}")
                logger.info(f"카테고리: {news['category_name']}")
                logger.info(f"본문 일부: {news['content'][:100]}...")
            
            logger.info(f"=== 카테고리 {category} 최신 뉴스 수집 완료 ===\n")
    
    # 모든 카테고리를 동시에 처리 (세마포어로 5개씩 제한)
    tasks = [process_category(category) for category in categories]
    await asyncio.gather(*tasks)

if __name__ == "__main__":
    asyncio.run(main()) 