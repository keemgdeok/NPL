import argparse
import os
import logging
import time
from transformers import BartForConditionalGeneration, PreTrainedTokenizerFast
import torch

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("summary-setup")

# 모델 정보
MODEL_NAME = "gogamza/kobart-summarization"
TEST_TEXT = "KoBART-summarization은 한국어 텍스트 요약을 위한 모델입니다. 이 모델은 SK텔레콤에서 개발한 KoBART를 기반으로 하여 한국어 요약 태스크에 특화되어 있습니다. 뉴스 기사나 긴 문서의 핵심 내용을 추출하여 간결하게 요약해주는 능력을 갖추고 있습니다."

def download_model(output_dir: str):
    """
    Hugging Face에서 KoBART 요약 모델을 다운로드하고 지정된 디렉토리에 저장합니다.
    
    Args:
        output_dir (str): 모델을 저장할 디렉토리 경로
    """
    start_time = time.time()
    logger.info(f"'{MODEL_NAME}' 모델 다운로드 시작...")
    
    # 출력 디렉토리 생성
    os.makedirs(output_dir, exist_ok=True)
    logger.info(f"출력 디렉토리: {output_dir}")
    
    try:
        # 모델 다운로드
        logger.info("모델 가중치 다운로드 중...")
        model = BartForConditionalGeneration.from_pretrained(MODEL_NAME)
        model.save_pretrained(output_dir)
        logger.info(f"모델 가중치 저장 완료: {output_dir}")
        
        # 토크나이저 다운로드
        logger.info("토크나이저 다운로드 중...")
        tokenizer = PreTrainedTokenizerFast.from_pretrained(MODEL_NAME)
        tokenizer.save_pretrained(output_dir)
        logger.info(f"토크나이저 저장 완료: {output_dir}")
        
        # 모델 테스트
        logger.info("다운로드한 모델 테스트 중...")
        test_model(model, tokenizer)
        
        elapsed_time = time.time() - start_time
        logger.info(f"모델 다운로드 및 저장 완료 (소요 시간: {elapsed_time:.2f}초)")
        
        # 저장된 파일 목록 출력
        logger.info("저장된 파일 목록:")
        for file in os.listdir(output_dir):
            file_path = os.path.join(output_dir, file)
            file_size = os.path.getsize(file_path) / (1024 * 1024)  # MB 단위로 변환
            logger.info(f"  - {file} ({file_size:.2f} MB)")
        
        return True
    except Exception as e:
        logger.error(f"모델 다운로드 중 오류 발생: {str(e)}", exc_info=True)
        return False

def test_model(model, tokenizer):
    """
    다운로드한 모델이 제대로 작동하는지 테스트합니다.
    
    Args:
        model: 요약 모델
        tokenizer: 토크나이저
    """
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    logger.info(f"테스트 장치: {device}")
    
    model.to(device)
    
    try:
        logger.info(f"테스트 텍스트: {TEST_TEXT[:50]}...")
        
        # 토큰화
        inputs = tokenizer(TEST_TEXT, return_tensors="pt", max_length=1024, truncation=True)
        inputs = inputs.to(device)
        
        # 요약 생성
        summary_ids = model.generate(
            inputs["input_ids"],
            max_length=128,
            min_length=32,
            num_beams=4,
            length_penalty=2.0,
            early_stopping=True
        )
        
        # 디코딩
        summary = tokenizer.decode(summary_ids[0], skip_special_tokens=True)
        
        logger.info(f"테스트 요약 결과: {summary}")
        logger.info("모델 테스트 성공!")
        return True
    except Exception as e:
        logger.error(f"모델 테스트 중 오류 발생: {str(e)}", exc_info=True)
        return False

def load_and_test_local_model(model_path: str):
    """
    로컬에 저장된 모델을 로드하고 테스트합니다.
    
    Args:
        model_path (str): 모델이 저장된 디렉토리 경로
        
    Returns:
        bool: 모델 로드 및 테스트 성공 여부
    """
    try:
        logger.info(f"로컬 모델 로드 중: {model_path}")
        model = BartForConditionalGeneration.from_pretrained(model_path)
        tokenizer = PreTrainedTokenizerFast.from_pretrained(model_path)
        
        logger.info("로컬 모델 테스트 중...")
        test_result = test_model(model, tokenizer)
        
        if test_result:
            logger.info("로컬 모델 로드 및 테스트 성공!")
        else:
            logger.warning("로컬 모델 테스트 실패")
        
        return test_result
    except Exception as e:
        logger.error(f"로컬 모델 로드 중 오류 발생: {str(e)}", exc_info=True)
        return False

def main():
    parser = argparse.ArgumentParser(description='KoBART 요약 모델 다운로드 및 설정')
    parser.add_argument('--output-dir', type=str, required=True,
                        help='모델을 저장할 디렉토리 경로')
    parser.add_argument('--test-only', action='store_true',
                        help='다운로드 없이 기존 모델만 테스트')
    
    args = parser.parse_args()
    
    if args.test_only:
        if os.path.exists(args.output_dir):
            load_and_test_local_model(args.output_dir)
        else:
            logger.error(f"지정된 모델 경로가 존재하지 않습니다: {args.output_dir}")
    else:
        download_model(args.output_dir)

if __name__ == "__main__":
    main() 