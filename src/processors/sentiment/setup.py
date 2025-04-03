import os
import sys
import logging
import torch
from transformers import AutoTokenizer, AutoModelForSequenceClassification
import argparse
from pathlib import Path
import time

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("setup-finbert")

def download_model(model_name: str, output_dir: str, use_cuda: bool = True):
    """모델을 다운로드하고 로컬에 저장합니다."""
    start_time = time.time()
    
    # 출력 디렉토리 생성
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    # 장치 설정
    device = torch.device('cuda' if torch.cuda.is_available() and use_cuda else 'cpu')
    logger.info(f"모델 다운로드 시작: {model_name} (장치: {device})")
    
    try:
        # 토크나이저와 모델 다운로드
        tokenizer = AutoTokenizer.from_pretrained(model_name)
        model = AutoModelForSequenceClassification.from_pretrained(model_name)
        
        # 저장 
        logger.info(f"토크나이저 저장 중: {output_dir}")
        tokenizer.save_pretrained(output_dir)
        
        logger.info(f"모델 저장 중: {output_dir}")
        model.save_pretrained(output_dir)
        
        # 모델 테스트
        test_sentence = "삼성전자의 3분기 영업이익이 전년 동기 대비 30% 증가했다."
        
        # 모델을 장치로 이동
        model.to(device)
        
        # 모델 레이블 수 확인
        num_labels = model.config.num_labels
        logger.info(f"모델 레이블 수: {num_labels}")
        
        # 추론 테스트
        logger.info("모델 추론 테스트 중...")
        inputs = tokenizer(test_sentence, return_tensors="pt", truncation=True, max_length=512).to(device)
        
        with torch.no_grad():
            outputs = model(**inputs)
            predictions = torch.softmax(outputs.logits, dim=-1)
            
        sentiment_scores = predictions[0].cpu().numpy()
        
        # 레이블 설정
        labels = ['negative', 'neutral', 'positive'] if num_labels == 3 else ['negative', 'positive']
        
        # 결과 출력
        logger.info(f"테스트 문장: '{test_sentence}'")
        logger.info(f"점수 배열: {sentiment_scores}")
        
        if len(sentiment_scores) == len(labels):
            predicted_idx = int(sentiment_scores.argmax())
            predicted_label = labels[predicted_idx]
            
            if num_labels == 3:
                logger.info(f"감정 분석 결과: {predicted_label}")
                logger.info(f"점수: 부정={sentiment_scores[0]:.4f}, 중립={sentiment_scores[1]:.4f}, 긍정={sentiment_scores[2]:.4f}")
            else:
                logger.info(f"감정 분석 결과: {predicted_label}")
                logger.info(f"점수: 부정={sentiment_scores[0]:.4f}, 긍정={sentiment_scores[1]:.4f}")
        else:
            logger.warning(f"레이블 수({len(labels)})와 출력 크기({len(sentiment_scores)})가 일치하지 않습니다")
            logger.info(f"레이블을 자동으로 조정합니다.")
            
            # 결과 인덱스 및 값 출력
            max_idx = sentiment_scores.argmax()
            logger.info(f"최대값 인덱스: {max_idx}, 값: {sentiment_scores[max_idx]:.4f}")
            
            # 모델 레이블 수 저장 (환경 설정에 필요)
            with open(os.path.join(output_dir, "labels_info.txt"), "w") as f:
                f.write(f"NUM_LABELS={len(sentiment_scores)}\n")
                f.write(f"MAX_SCORE_INDEX={max_idx}\n")
                f.write(f"SCORE_SHAPE={sentiment_scores.shape}\n")
        
        # 완료 시간 기록
        elapsed_time = time.time() - start_time
        logger.info(f"모델 다운로드 및 저장 완료 (소요시간: {elapsed_time:.2f}초)")
        
        # 캐시 경로 안내
        cache_dir = os.path.expanduser("~/.cache/huggingface/transformers")
        logger.info(f"기본 모델 캐시 경로: {cache_dir}")
        logger.info(f"로컬 모델 경로: {output_path.absolute()}")
        
        return True
    
    except Exception as e:
        logger.error(f"모델 다운로드 실패: {str(e)}")
        return False

def main():
    parser = argparse.ArgumentParser(description="KR-FinBert-SC 모델 다운로드 및 설정 도구")
    parser.add_argument("--model-name", type=str, default="snunlp/KR-FinBert-SC",
                      help="다운로드할 모델 이름 (기본값: snunlp/KR-FinBert-SC)")
    parser.add_argument("--output-dir", type=str, default="./models/kr-finbert-sc",
                      help="모델을 저장할 디렉토리 (기본값: ./models/kr-finbert-sc)")
    parser.add_argument("--use-cpu", action="store_true",
                      help="GPU 대신 CPU 사용 (기본값: False)")
    
    args = parser.parse_args()
    
    # 모델 다운로드 실행
    success = download_model(
        model_name=args.model_name, 
        output_dir=args.output_dir,
        use_cuda=not args.use_cpu
    )
    
    if success:
        logger.info("=== 모델 사용 방법 ===")
        logger.info("감정 분석을 실행하려면 다음 명령을 사용하세요:")
        logger.info(f"python -m src.processors.sentiment.run_processor --mode stream --model-path {args.output_dir}")
        logger.info("또는 배치 처리를 위해:")
        logger.info(f"python -m src.processors.sentiment.run_processor --mode batch --category economy --days 7 --model-path {args.output_dir}")
        sys.exit(0)
    else:
        logger.error("모델 설정 실패")
        sys.exit(1)

if __name__ == "__main__":
    main() 