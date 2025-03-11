import argparse
import asyncio
import logging
from .scraper.manager import ScraperManager

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def async_main(args):
    """비동기 메인 함수"""
    # 스크래퍼 매니저 초기화
    manager = ScraperManager(
        kafka_bootstrap_servers=args.kafka_servers,
        interval=args.interval
    )
    
    try:
        if args.run_once:
            # 단일 실행
            logger.info("모든 스크래퍼를 한 번만 실행")
            await manager.run_scrapers_once()
        else:
            # 주기적 실행
            logger.info(f"모든 스크래퍼를 {args.interval}초 간격으로 주기적으로 실행")
            await manager.run_periodic()
            
    except KeyboardInterrupt:
        logger.info("\n수집이 사용자에 의해 중단되었습니다")
    except Exception as e:
        logger.error(f"수집 중 오류 발생: {str(e)}")
    finally:
        manager.close()

def main():
    """명령행 인자를 파싱하고 비동기 메인 함수를 실행"""
    parser = argparse.ArgumentParser(description='뉴스 수집기')
    parser.add_argument('--kafka-servers', type=str, default='localhost:9092',
                      help='Kafka 부트스트랩 서버 주소 (기본값: localhost:9092)')
    parser.add_argument('--interval', type=int, default=3600,
                      help='주기적 실행 시 수집 간격(초) (기본값: 3600)')
    parser.add_argument('--run-once', action='store_true',
                      help='한 번만 실행하고 종료 (기본: 주기적 실행)')
    
    args = parser.parse_args()
    
    # 비동기 실행
    asyncio.run(async_main(args))

if __name__ == "__main__":
    main() 