import argparse
import os
import logging
import time
import nltk

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("summary-setup")

def download_nltk_punkt():
    """
    NLTK의 'punkt' 토크나이저 모델을 다운로드합니다.
    TextSummarizer에서 문장 토큰화를 위해 필요합니다.
    """
    logger.info("NLTK 'punkt' 리소스 다운로드 시도...")
    try:
        nltk.download('punkt', quiet=False)
        logger.info("NLTK 'punkt' 리소스가 성공적으로 확인/다운로드되었습니다.")
        # 간단한 테스트 (punkt가 실제로 사용 가능한지 확인하는 더 좋은 방법이 있을 수 있음)
        try:
            nltk.sent_tokenize("이것은 punkt 테스트 문장입니다. 잘 작동하나요?")
            logger.info("NLTK 'punkt' 토크나이저 사용 가능 확인.")
        return True
    except Exception as e:
            logger.error(f"NLTK 'punkt' 사용 테스트 중 오류: {e}")
            logger.error("NLTK 'punkt'가 올바르게 설치되지 않았을 수 있습니다. 수동 확인이 필요합니다.")
        return False

    except Exception as e:
        logger.error(f"NLTK 'punkt' 다운로드 중 오류 발생: {str(e)}", exc_info=True)
        logger.error("인터넷 연결을 확인하거나, 수동으로 NLTK punkt를 설치해야 할 수 있습니다.")
        logger.error(" (Python 인터프리터에서 import nltk; nltk.download('punkt') 실행)")
        return False

def main():
    parser = argparse.ArgumentParser(description='Summary 프로세서 환경 설정 (NLTK punkt 다운로드)')
    args = parser.parse_args()
    
    logger.info("Summary 프로세서 환경 설정 시작...")
    
    # NLTK punkt 다운로드 실행
    punkt_downloaded = download_nltk_punkt()
    
    if punkt_downloaded:
        logger.info("NLTK 'punkt' 리소스 준비 완료.")
    else:
        logger.warning("NLTK 'punkt' 리소스 준비에 실패했습니다. 요약 기능이 제한될 수 있습니다.")
        logger.warning("수동으로 NLTK punkt를 다운로드해주세요. (Python: import nltk; nltk.download('punkt'))")

    logger.info("Summary 프로세서 환경 설정 완료.")

if __name__ == "__main__":
    main() 