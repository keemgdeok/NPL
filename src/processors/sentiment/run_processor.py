import argparse
from .processor import SentimentProcessor
import logging
import os
from ...collectors.utils.config import Config
import torch

# 로깅 설정
logging.basicConfig(
    level=getattr(logging, Config.LOG_LEVEL),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("sentiment-processor")

def main():
    # 환경 검증
    try:
        Config.validate()
    except ValueError as e:
        logger.error(f"설정 오류: {str(e)}")
        return
    
    parser = argparse.ArgumentParser(description='금융 뉴스 감정 분석기 (KR-FinBert-SC 모델 사용)')
    parser.add_argument('--mode', choices=['stream'], default='stream',
                      help='처리 모드 선택 (stream: 실시간)')
    parser.add_argument('--model-path', type=str, default='models/kr-finbert-sc',
                      help='로컬에 저장된 모델 경로 (없으면 Hugging Face에서 다운로드)')
    parser.add_argument('--list-topics', action='store_true',
                      help='처리 가능한 Kafka 토픽 목록 출력')
    parser.add_argument('--idle-timeout', type=int, default=10,
                      help='스트림 모드에서 지정된 시간(초) 동안 메시지가 없으면 자동 종료 (기본값: 무제한)')
    
    args = parser.parse_args()
    
    # 토픽 목록 출력
    if args.list_topics:
        print("\n사용 가능한 Kafka 토픽 목록:")
        print("=" * 50)
        print("입력 토픽 (processed):")
        for category in Config.CATEGORIES:
            print(f"  - {Config.KAFKA_TOPIC_PREFIX}.{category}.processed")
        print("\n출력 토픽 (sentiment):")
        for category in Config.CATEGORIES:
            print(f"  - {Config.KAFKA_TOPIC_PREFIX}.{category}.sentiment")
        print("=" * 50)
        return
    
    # 프로세서 변수 초기화
    processor = None
    
    try:
        # 모델 경로 로깅 및 확인
        if args.model_path:
            if os.path.exists(args.model_path):
                logger.info(f"로컬 모델 경로 사용: {args.model_path}")
            else:
                logger.warning(f"지정된 모델 경로가 존재하지 않습니다: {args.model_path}")
                logger.info("모델을 다운로드하려면 다음 명령을 실행하세요:")
                logger.info(f"python -m src.processors.sentiment.setup --output-dir={args.model_path}")
                return
        
        logger.info(f"금융 뉴스 감성 분석 시작 - KR-FinBert-SC 모델 사용 (디바이스: {torch.device('cuda' if torch.cuda.is_available() else 'cpu')})")
        logger.info(f"카테고리 목록: {', '.join([f'{k}({v})' for k, v in Config.CATEGORIES.items()])}")
        
        # 프로세서 초기화 - 여기서 모든 리소스(Kafka, MongoDB)가 설정됨
        processor = SentimentProcessor(model_path=args.model_path)
        
        # 처리 모드에 따라 실행
        if args.mode == 'stream':
            logger.info("스트림 처리 모드 시작...")
            if args.idle_timeout:
                logger.info(f"자동 종료 설정: {args.idle_timeout}초 동안 메시지 없으면 종료")
            logger.info(f"다음 토픽들을 구독합니다: {', '.join([f'{Config.KAFKA_TOPIC_PREFIX}.{c}.processed' for c in Config.CATEGORIES])}")
            processor.process_stream()
        else:
            logger.info(f"배치 처리 모드 시작 - 최근 {args.days}일 데이터 처리...")
            if args.category:
                category_name = Config.CATEGORIES.get(args.category, "")
                logger.info(f"카테고리 필터: {args.category} ({category_name})")
            processor.process_batch(args.category, args.days)
            
    except KeyboardInterrupt:
        logger.info("사용자에 의해 처리가 중단되었습니다")
    except Exception as e:
        logger.error(f"처리 중 오류 발생: {str(e)}", exc_info=True)
    finally:
        # 프로세서가 초기화되었을 때만 리소스 정리
        if processor is not None:
            try:
                logger.info("리소스 정리 중...")
                processor.close()
                logger.info("리소스 정리 완료")
            except Exception as cleanup_error:
                logger.error(f"리소스 정리 중 오류 발생: {str(cleanup_error)}")
        
        logger.info("처리 완료")

if __name__ == "__main__":
    main() 