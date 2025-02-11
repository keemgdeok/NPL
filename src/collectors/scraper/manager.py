from typing import List, Type
import asyncio
import logging
from datetime import datetime, timedelta

from .base import BaseScraper
from .hankyung import HankyungScraper
from .mk_popular import MKPopularScraper
from .naver import NaverScraper

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class ScraperManager:
    """뉴스 스크래퍼 관리자
    
    여러 뉴스 스크래퍼를 동시에 실행하고 관리하는 클래스입니다.
    
    Attributes:
        scrapers (List[BaseScraper]): 실행할 스크래퍼 목록
        interval (int): 수집 주기 (초)
    """
    
    def __init__(self, kafka_bootstrap_servers: str, interval: int = 3600):
        """
        Args:
            kafka_bootstrap_servers (str): Kafka 부트스트랩 서버 주소
            interval (int, optional): 수집 주기 (초). 기본값은 1시간.
        """
        self.scrapers: List[BaseScraper] = [
            HankyungScraper(kafka_bootstrap_servers),
            MKPopularScraper(kafka_bootstrap_servers),
            NaverScraper(kafka_bootstrap_servers)
        ]
        self.interval = interval
    
    async def run_scraper(self, scraper: BaseScraper):
        """개별 스크래퍼 실행"""
        logger.info(f"\n=== {scraper.name} 스크래퍼 시작 ===")
        try:
            await scraper.collect_all_categories()
            logger.info(f"=== {scraper.name} 스크래퍼 완료 ===\n")
        except Exception as e:
            logger.error(f"{scraper.name} 스크래퍼 실행 중 오류 발생: {str(e)}")
    
    async def run_scrapers_once(self):
        """모든 스크래퍼를 한 번 실행"""
        tasks = []
        
        for scraper in self.scrapers:
            task = asyncio.create_task(self.run_scraper(scraper))
            tasks.append(task)
        
        # 모든 스크래퍼 동시 실행
        await asyncio.gather(*tasks, return_exceptions=True)
    
    async def run_periodic(self):
        """주기적으로 스크래퍼 실행"""
        while True:
            start_time = datetime.now()
            logger.info(f"\n=== 스크래퍼 실행 시작: {start_time} ===")
            
            try:
                await self.run_scrapers_once()
                logger.info("=== 모든 스크래퍼 실행 완료 ===\n")
                
            except Exception as e:
                logger.error(f"스크래퍼 실행 중 오류 발생: {str(e)}")
            
            # 다음 실행 시간 계산
            end_time = datetime.now()
            elapsed = (end_time - start_time).total_seconds()
            sleep_time = max(0, self.interval - elapsed)
            
            logger.info(f"다음 실행까지 {sleep_time:.2f}초 대기")
            await asyncio.sleep(sleep_time)
    
    def close(self):
        """모든 스크래퍼의 리소스 정리"""
        for scraper in self.scrapers:
            scraper.close()

async def test_manager():
    """매니저 테스트 함수"""
    # Kafka 서버 주소 설정
    kafka_servers = "localhost:9092"
    
    # 스크래퍼 매니저 생성 (테스트용으로 10분 간격 설정)
    manager = ScraperManager(kafka_servers, interval=600)
    
    try:
        # 한 번만 실행
        logger.info("스크래퍼 테스트 시작")
        await manager.run_scrapers_once()
        logger.info("스크래퍼 테스트 완료")
        
    except KeyboardInterrupt:
        logger.info("사용자에 의해 중단됨")
    except Exception as e:
        logger.error(f"테스트 중 오류 발생: {str(e)}")
    finally:
        manager.close()

if __name__ == "__main__":
    asyncio.run(test_manager()) 