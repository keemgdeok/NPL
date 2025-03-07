import argparse
import logging
import os
from .processor import TopicProcessor

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def main():
    parser = argparse.ArgumentParser(description='뉴스 기사 토픽 모델링 처리기')
    parser.add_argument('--mode', choices=['stream', 'batch', 'train', 'summarize'], default='stream',
                      help='처리 모드 선택 (stream: 실시간, batch: 배치, train: 모델 학습, summarize: 주제 요약)')
    parser.add_argument('--category', type=str,
                      help='처리할 카테고리 (배치 모드에서만 사용)')
    parser.add_argument('--days', type=int, default=30,
                      help='처리할 기간 (일 단위, 배치 모드에서는 처리 기간, 학습 모드에서는 학습 데이터 기간)')
    parser.add_argument('--n_topics', type=int, default=10,
                      help='토픽 모델의 토픽 수')
    parser.add_argument('--model_path', type=str, default='models/korean_news_topics',
                      help='모델 저장/로드 경로')
    
    # CPU 최적화 설정 (스레드 수 등)
    for env_var in ['OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS', 'OMP_NUM_THREADS', 'NUMEXPR_NUM_THREADS']:
        if env_var not in os.environ:
            os.environ[env_var] = str(min(os.cpu_count() or 4, 4))  # 최대 4개 스레드로 제한
    
    args = parser.parse_args()
    
    logger.info("토픽 프로세서 초기화 중...")
    processor = TopicProcessor(n_topics=args.n_topics)
    
    try:
        if args.mode == 'stream':
            logger.info("스트림 처리 모드 시작...")
            processor.process_stream()
        elif args.mode == 'batch':
            logger.info(f"배치 처리 모드 시작 (기간: {args.days}일, 카테고리: {args.category or '전체'})...")
            processor.process_batch(args.category, args.days)
        elif args.mode == 'train':
            logger.info(f"모델 학습 모드 시작 (데이터 기간: {args.days}일)...")
            processor.train_model(args.days)
            logger.info("모델 학습 완료")
        elif args.mode == 'summarize':
            # 토픽 모델러에서 주제 요약 정보 출력
            logger.info("주제 요약 정보 생성 중...")
            topic_summary = processor.topic_modeler.summarize_topics()
            
            logger.info(f"총 {topic_summary['total_topics']}개 주제 발견")
            for topic in topic_summary['topics']:
                logger.info(f"주제 {topic['id']} ({topic['label']}): {', '.join(topic['keywords'])}")
                logger.info(f"  - 문서 수: {topic['size']}")
                if topic['representative_docs']:
                    logger.info(f"  - 대표 문서: {topic['representative_docs'][0][:100]}...")
                logger.info("---")
            
    except KeyboardInterrupt:
        logger.info("\n처리가 사용자에 의해 중단되었습니다.")
    except Exception as e:
        logger.error(f"처리 중 오류 발생: {str(e)}")
    finally:
        processor.close()

if __name__ == "__main__":
    main() 