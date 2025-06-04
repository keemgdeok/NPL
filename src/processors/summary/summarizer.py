from typing import Dict, Any, List
import torch
from transformers import AutoTokenizer, T5ForConditionalGeneration
import logging
import time
import nltk

logger = logging.getLogger("text-summarizer")

# 짧은 텍스트 기준 상수화
MIN_TEXT_LENGTH_FOR_SUMMARY = 10
DEFAULT_MODEL_NAME = "eenzeenee/t5-base-korean-summarization"

class TextSummarizer:
    def __init__(self, model_name: str = DEFAULT_MODEL_NAME, model_path: str = None):
        """T5 요약 모델 초기화
        
        Args:
            model_name (str): Hugging Face T5 계열 모델 이름. model_path가 제공되지 않을 경우 사용됩니다.
                              기본값은 "eenzeenee/t5-base-korean-summarization" 입니다.
            model_path (str, optional): 로컬에 저장된 모델 경로. 제공될 경우 model_name 대신 사용됩니다.
                                       Defaults to None.
        """
        self.device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
        
        self.model_identifier = model_path or model_name
        logger.info(f"요약 모델 로드 중 (모델: {self.model_identifier}, 디바이스: {self.device})")
        start_time = time.time()
        
        self.tokenizer = None
        self.model = None

        # nltk punkt 리소스 다운로드는 setup.py 또는 외부 스크립트에서 처리하는 것을 권장
        # 여기서는 NLTK 사용 가능성을 가정합니다. 필요시 사용자에게 nltk.download('punkt') 실행 안내.
        # try:
        #     nltk.download('punkt', quiet=True)
        # except Exception as e:
        #     logger.warning(f"nltk punkt 리소스 다운로드 중 오류 발생 (수동 설치 필요할 수 있음): {e}")

        try:
            load_from = self.model_identifier
            
            logger.info(f"모델 로드 경로: {load_from}")
            self.tokenizer = AutoTokenizer.from_pretrained(load_from)
            self.model = T5ForConditionalGeneration.from_pretrained(load_from)
            
            self.model.to(self.device)
            model_load_time = time.time() - start_time
            logger.info(f"모델 로드 완료 (소요시간: {model_load_time:.2f}초)")
            
        except Exception as e:
            logger.error(f"모델 로드 실패 ({self.model_identifier}): {str(e)}")
            raise
        
        # 성능 통계
        self.total_summarized_count = 0 # 요약 시도된 전체 텍스트 수 (스킵 포함)
        self.total_processing_time = 0.0  # 실제 모델 생성에 소요된 총 시간
    
    def _get_sentence_count(self, text: str) -> int:
        """주어진 텍스트의 문장 수를 계산합니다."""
        if not text or not text.strip():
            return 0
        try:
            sentences = nltk.sent_tokenize(text)
            return len([s for s in sentences if s.strip()])
        except Exception as e:
            logger.warning(f"문장 수 계산 중 오류 발생 (텍스트: '{text[:30]}...'): {e}")
            # 단순 fallback: 비어있지 않으면 최소 1문장으로 간주
            return 1

    def _get_generate_kwargs(
        self,
        summary_min_length: int,
        summary_max_length: int,
        num_beams: int,
        repetition_penalty: float,
        no_repeat_ngram_size: int,
        top_k: int,
        top_p: float,
        temperature: float,
        do_sample: bool
    ) -> Dict[str, Any]:
        """model.generate에 전달할 파라미터 딕셔너리를 생성합니다."""
        kwargs = {
            "min_length": summary_min_length,
            "max_length": summary_max_length,
            "num_beams": num_beams,
            "early_stopping": True,
        }
        if do_sample:
            kwargs["do_sample"] = True
            kwargs["top_k"] = top_k
            kwargs["top_p"] = top_p
            kwargs["temperature"] = temperature
            kwargs["repetition_penalty"] = repetition_penalty
            kwargs["no_repeat_ngram_size"] = no_repeat_ngram_size
        else:
            kwargs["do_sample"] = False
            if num_beams > 1: # Beam search 일 때
                kwargs["repetition_penalty"] = repetition_penalty
                kwargs["no_repeat_ngram_size"] = no_repeat_ngram_size
        return kwargs

    def summarize(
        self, 
        text: str, 
        input_max_length: int = 1024,
        summary_min_length: int = 30,
        summary_max_length: int = 256,
        num_beams: int = 4,
        repetition_penalty: float = 2.5,
        no_repeat_ngram_size: int = 3,
        top_k: int = 50,
        top_p: float = 0.95,
        temperature: float = 1.0,
        do_sample: bool = True
    ) -> Dict[str, Any]:
        """텍스트 요약 수행 (단일 텍스트)"""
        start_time = time.time()
        
        if not text or len(text.strip()) == 0:
            logger.warning("빈 텍스트가 입력되었습니다")
            return {"summary": "", "original_length": 0, "summary_length": 0, "sentence_count": 0, "processing_time_seconds": 0.0, "model_name_used": self.model_identifier}
        
        prefixed_text = f"summarize: {text}"

        if len(text.strip()) < MIN_TEXT_LENGTH_FOR_SUMMARY: # 너무 짧은 텍스트는 원본 반환
            logger.debug(f"텍스트가 너무 짧아 원본을 반환 (길이: {len(text)}, 기준: {MIN_TEXT_LENGTH_FOR_SUMMARY}자)")
            original_sentence_count = self._get_sentence_count(text)
                
            # item_processing_time = time.time() - start_time # 모델 연산이 아니므로 측정 불필요
            self.total_summarized_count += 1 # 시도 횟수에는 포함
            # self.total_processing_time은 모델 연산이 아니므로 증가시키지 않음

            return {
                "summary": text, 
                    "original_length": len(text),
                "summary_length": len(text),
                "sentence_count": original_sentence_count,
                "processing_time_seconds": 0.0, # 모델 연산 없음
                "model_name_used": "N/A (too short)"
            }

        inputs = self.tokenizer(
            prefixed_text,
            return_tensors="pt",
            max_length=input_max_length,
            truncation=True,
            padding=False # 단일 입력이므로 패딩 불필요 또는 "max_length"
        ).to(self.device)
        
        generate_kwargs = self._get_generate_kwargs(
            summary_min_length, summary_max_length, num_beams, repetition_penalty,
            no_repeat_ngram_size, top_k, top_p, temperature, do_sample
        )

        model_inference_start_time = time.time()
        with torch.no_grad():
            summary_ids = self.model.generate(
                inputs["input_ids"],
                attention_mask=inputs["attention_mask"],
                **generate_kwargs
            )
        model_inference_time = time.time() - model_inference_start_time
        
        summary = self.tokenizer.decode(summary_ids[0], skip_special_tokens=True)
        
        if not summary.strip():
            logger.warning(f"생성된 요약문이 비어있습니다. 원본 텍스트 길이: {len(text)}")

        sentence_count = self._get_sentence_count(summary)

        total_item_time = time.time() - start_time
        
        result = {
            "summary": summary,
            "original_length": len(text),
            "summary_length": len(summary),
            "sentence_count": sentence_count,
            "processing_time_seconds": round(model_inference_time, 4), # 모델 생성 시간만
            "model_name_used": self.model.config._name_or_path # 실제 사용된 모델 이름
        }
        
        self.total_summarized_count += 1
        self.total_processing_time += model_inference_time
        
        if self.total_summarized_count % 100 == 0:
            avg_model_time = self.total_processing_time / self.total_summarized_count if self.total_summarized_count > 0 else 0
            logger.info(
                f"누적 성능 통계 (summarize 호출 포함) - 평균 모델 생성 시간: {avg_model_time:.4f}초/텍스트, "
                f"총 요약 시도 개수: {self.total_summarized_count}"
            )
        
        return result
        
    def summarize_batch(
        self, 
        texts: List[str], 
        input_max_length: int = 1024,
        summary_min_length: int = 30,
        summary_max_length: int = 256,
        num_beams: int = 4,
        repetition_penalty: float = 2.5,
        no_repeat_ngram_size: int = 3,
        top_k: int = 50,
        top_p: float = 0.95,
        temperature: float = 1.0,
        do_sample: bool = True
    ) -> List[Dict[str, Any]]:
        """여러 텍스트의 요약 수행 (직접 토큰화 및 model.generate 사용)"""
        if not texts:
            return []

        start_batch_function_time = time.time()
        
        num_input_texts = len(texts)
        final_results = [None] * num_input_texts
        
        texts_to_process_indices = [] # 실제 모델에 입력될 텍스트의 원본 인덱스
        texts_for_model_input = []    # 모델에 입력될 접두사가 붙은 텍스트

        for i, text_content in enumerate(texts):
            if not text_content or len(text_content.strip()) < MIN_TEXT_LENGTH_FOR_SUMMARY: # 너무 짧거나 빈 텍스트
                logger.debug(f"인덱스 {i}: 텍스트가 너무 짧거나 비어서 원본 반환 (길이: {len(text_content.strip())}, 기준: {MIN_TEXT_LENGTH_FOR_SUMMARY}자)")
                s_count = self._get_sentence_count(text_content)
                final_results[i] = {
                    "summary": text_content,
                    "original_length": len(text_content),
                    "summary_length": len(text_content),
                    "sentence_count": s_count,
                    "processing_time_seconds": 0.0,
                    "model_name_used": "N/A (too short or empty)"
                }
            else:
                texts_to_process_indices.append(i)
                texts_for_model_input.append(f"summarize: {text_content}")

        actual_batch_size = len(texts_for_model_input)
        model_processing_time_for_batch = 0.0
        decoded_summaries = []

        if actual_batch_size > 0:
            try:
                batch_inputs = self.tokenizer(
                    texts_for_model_input, 
            return_tensors="pt", 
                    padding="longest", 
                    truncation=True, 
                    max_length=input_max_length
        ).to(self.device)
        
                generate_kwargs = self._get_generate_kwargs(
                    summary_min_length, summary_max_length, num_beams, repetition_penalty,
                    no_repeat_ngram_size, top_k, top_p, temperature, do_sample
                )
                
                logger.info(f"Model.generate 배치 요약 시작: {actual_batch_size}개 텍스트, Params: {generate_kwargs}")
                
                model_inference_start_time = time.time()
                with torch.no_grad(): # Linter error 수정: with 블록 내부로 generate 호출 이동
                    summary_ids_batch = self.model.generate(
                        batch_inputs["input_ids"],
                        attention_mask=batch_inputs["attention_mask"],
                        **generate_kwargs
                    )
                model_processing_time_for_batch = time.time() - model_inference_start_time
                logger.info(f"Model.generate 배치 요약 완료 (소요시간: {model_processing_time_for_batch:.2f}초)")

                decoded_summaries = self.tokenizer.batch_decode(summary_ids_batch, skip_special_tokens=True)
            
            except Exception as e: # Linter error 수정: except 블록을 try와 같은 레벨로
                logger.error(f"summarize_batch 중 Model.generate 오류 발생: {e}", exc_info=True)
                # 오류 발생 시, 이 배치에 포함된 모든 텍스트에 대해 에러 결과 생성
                error_summary_text = f"Error during batch summarization: {str(e)}"
                decoded_summaries = [error_summary_text] * actual_batch_size
                # 모델 처리 시간은 오류 발생까지의 시간 또는 0으로 설정 가능
                if model_processing_time_for_batch == 0.0 and 'model_inference_start_time' in locals():
                     model_processing_time_for_batch = time.time() - model_inference_start_time
                # 추가: 오류 발생 시에도 model_processing_time_for_batch 기록
                elif 'model_inference_start_time' in locals() and model_inference_start_time > 0: # 이미 시간이 기록 시작되었다면
                    model_processing_time_for_batch = time.time() - model_inference_start_time

        # 결과 조합
        avg_model_time_per_item = model_processing_time_for_batch / actual_batch_size if actual_batch_size > 0 else 0.0
        
        for batch_idx, original_idx in enumerate(texts_to_process_indices):
            original_text = texts[original_idx] # 스킵되지 않은 원본 텍스트
            summary_text = decoded_summaries[batch_idx]

            if "Error during batch summarization:" in summary_text:
                s_count = 0
                logger.warning(f"인덱스 {original_idx}: 배치 요약 중 오류로 처리됨. 원본: '{original_text[:50]}...'")
            else:
                if not summary_text.strip():
                    logger.warning(f"인덱스 {original_idx}: 배치 요약 결과 비어있음. 원본: '{original_text[:50]}...'")
                s_count = self._get_sentence_count(summary_text)
            
            final_results[original_idx] = {
                "summary": summary_text,
                "original_length": len(original_text),
                "summary_length": len(summary_text),
                "sentence_count": s_count,
                "processing_time_seconds": round(avg_model_time_per_item, 4),
                "model_name_used": self.model.config._name_or_path if not "Error during batch summarization:" in summary_text else "N/A (error in batch)"
            }

        self.total_summarized_count += num_input_texts # 전체 시도 횟수 카운트
        self.total_processing_time += model_processing_time_for_batch # 실제 모델 연산 시간만 더함
        
        total_batch_function_time = time.time() - start_batch_function_time
        
        logger.info(
            f"summarize_batch 완료: 총 입력 {num_input_texts}개, 실제 모델 처리 {actual_batch_size}개. "
            f"모델 생성 총 시간: {model_processing_time_for_batch:.2f}초. 함수 총 실행 시간: {total_batch_function_time:.2f}초."
        )
        if self.total_summarized_count > 0 and actual_batch_size > 0: # 실제 연산이 있었던 경우에만 누적 통계 업데이트 로깅
            avg_model_time_overall = self.total_processing_time / self.total_summarized_count 
            logger.info(
                f"누적 성능 통계 - 평균 모델 생성 시간 (전체 시도 기준, 실제 연산만 합산): {avg_model_time_overall:.4f}초/텍스트, "
                f"총 요약 시도 개수: {self.total_summarized_count}"
            )
        
        return final_results

# 사용 예시 (테스트용)
if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    
    # NLTK punkt 다운로드를 main 실행 시점에 시도 (테스트 용이성을 위해)
    try:
        logger.info("NLTK punkt 리소스 확인/다운로드 중...")
        nltk.download('punkt', quiet=False) 
        logger.info("NLTK punkt 리소스 준비 완료.")
    except Exception as e:
        logger.error(f"NLTK punkt 리소스 다운로드 실패. 수동 설치가 필요할 수 있습니다: {e}")
        exit() 

    try:
        # 기본 모델 사용
        summarizer = TextSummarizer() 
    except Exception as e:
        logger.error(f"TextSummarizer 초기화 실패: {e}", exc_info=True)
        exit() # 초기화 실패 시 종료

    # --- 단일 테스트 케이스 --- 
    sample_text_long = '''
    
유영상 SK텔레콤 대표가 위약금 면제 시 250만 명 이상의 가입자가 이탈할 거라고 예측했다. 인당 위약금도 10만 원 이상, 총 손실 규모는 최소 2천500억원이 될 것으로 내다봤다.

유 대표는 국회 과학기술정보방송통신위원회(과방위)에 출석해 이훈기 더불어민주당 의원의 '위약금 면제 시 번호이동 하는 사람이 얼마나 생길 것으로 예상하느냐'는 질문에 "해킹 사태 이후로 25만 명 정도 이탈했는데, 지금 보다 10배 이상일 것 같다"고 말했다.

1인당 평균 위약금은 "최소 10만 원을 넘을 것으로 예상한다"고 했다.

이에 이 의원이 "전날 SK텔레콤이 전달한 자료는 위약금 면제 시 수조 원의 손실이 추정된다고 했는데, 위약금만 따지면 2500억 원이 아니냐"고 반문했다.

이날 박정훈 국민의힘 의원도 "시장점유율 잃는 것 때문에 (위약금 면제를) 소극적으로 하는 거라고 볼 수 있지 않느냐"고 질의했다.

유 대표는 "(가입자 이탈이) 최대 500만 명까지도 가능하다고 생각하고, 위약금뿐 아니라 3년 치 매출까지 고려하면 7조 원 이상 손실도 예상하고 있다"고 답했다.

유 대표는 위약금 논의 절차에 대해선 "지금까지 두 번 이사회를 개최해 현재 상황을 보고하고 위약금을 논의했다"며 "법적 문제뿐 아니라 회사 손실 규모도 있고, 여러 이동통신 생태계 차별화 문제를 종합적으로 검토해야 하는 만큼 지금 단계에서는 결정하기 어렵다"고 말했다.

    '''

    print("\n--- 단일 텍스트 요약 테스트 (기본 설정: Beam Search) ---")
    # 요약 파라미터는 TextSummarizer의 기본값 또는 summarize 메서드 기본값 사용
    summary_result = summarizer.summarize(sample_text_long, do_sample=False) 
    
    # f-string 오류를 피하기 위해 replace 결과를 미리 변수에 저장
    original_text_display = sample_text_long[:200].replace('\n', ' ')

    # 수정된 print 문
    print(f"\n원본 (첫 200자): {original_text_display} ... ")
    print(f"\n요약 결과:")
    print(f"요약문: {summary_result.get('summary', 'N/A')}")
    print(f"상세 정보: {summary_result}")

    # --- 기존 다른 테스트 케이스들 제거 --- 

    # 최종 누적 성능 통계 제거 (단일 테스트에서는 의미 적음)
    # if summarizer.total_summarized_count > 0:
    #     avg_time_final = summarizer.total_processing_time / summarizer.total_summarized_count if summarizer.total_summarized_count else 0
    #     logger.info(
    #         f"최종 누적 성능 통계 (main 종료 시점) - 평균 모델 생성 시간: {avg_time_final:.4f}초/텍스트, "
    #         f"총 요약 시도 개수: {summarizer.total_summarized_count}"
    #     ) 