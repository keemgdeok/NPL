from typing import Dict, Any, List, Tuple
import torch
from transformers import PreTrainedTokenizerFast, BartForConditionalGeneration
import logging
import time
import numpy as np

logger = logging.getLogger("text-summarizer")

class TextSummarizer:
    def __init__(self, model_path: str = None):
        """KoBART 요약 모델 초기화
        
        Args:
            model_path: 로컬에 저장된 모델 경로 (없으면 Hugging Face에서 다운로드)
        """
        self.device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
        
        logger.info(f"요약 모델 로드 중 (디바이스: {self.device})")
        start_time = time.time()
        
        try:
            # 로컬 경로가 제공된 경우 해당 경로에서 로드
            if model_path:
                logger.info(f"로컬 모델 경로에서 로드: {model_path}")
                self.tokenizer = PreTrainedTokenizerFast.from_pretrained(model_path)
                self.model = BartForConditionalGeneration.from_pretrained(model_path)
            else:
                # 아니면 Hugging Face에서 다운로드
                logger.info("Hugging Face에서 로드: gogamza/kobart-summarization")
                self.tokenizer = PreTrainedTokenizerFast.from_pretrained("gogamza/kobart-summarization")
                self.model = BartForConditionalGeneration.from_pretrained("gogamza/kobart-summarization")
            
            self.model.to(self.device)
            load_time = time.time() - start_time
            logger.info(f"모델 로드 완료 (소요시간: {load_time:.2f}초)")
            
        except Exception as e:
            logger.error(f"모델 로드 실패: {str(e)}")
            raise
        
        # 성능 통계
        self.total_summarized = 0
        self.total_time = 0
    
    def summarize(self, text: str, max_length: int = 1024, summary_max_length: int = 128, num_beams: int = 5) -> Dict[str, Any]:
        """텍스트 요약 수행
        
        Args:
            text: 요약할 텍스트
            max_length: 입력 토큰 최대 길이
            summary_max_length: 요약 결과 최대 길이 (사용하지 않음, 항상 3-5 문장으로 요약)
            num_beams: 빔 서치 크기
            
        Returns:
            요약 결과 딕셔너리 (요약문, 원본 길이, 요약 길이)
        """
        start_time = time.time()
        
        # 빈 텍스트 처리
        if not text or len(text.strip()) == 0:
            logger.warning("빈 텍스트가 입력되었습니다")
            return {"summary": "", "original_length": 0, "summary_length": 0}
        
        # 입력 텍스트가 너무 짧은 경우
        if len(text) < 100:
            logger.debug(f"텍스트가 너무 짧아 요약하지 않음 (길이: {len(text)})")
            return {"summary": text, "original_length": len(text), "summary_length": len(text)}
            
        # 3-5 문장에 해당하는 토큰 길이 설정
        # 한국어에서 평균적으로 한 문장은 약 20-40 토큰 정도임
        min_sentences = 3
        max_sentences = 5
        
        # 문장당 평균 30 토큰으로 가정
        token_per_sentence = 30
        fixed_min_length = min_sentences * token_per_sentence  # 3문장 = 약 90 토큰
        fixed_max_length = max_sentences * token_per_sentence  # 5문장 = 약 150 토큰
        
        logger.debug(f"요약 길이 고정: {min_sentences}-{max_sentences}문장 (약 {fixed_min_length}-{fixed_max_length} 토큰)")
        
        # 입력 길이가 모델 최대 길이를 초과하는 경우 청크 단위로 처리
        tokenized_text = self.tokenizer.tokenize(text)
        if len(tokenized_text) > max_length:
            logger.debug(f"텍스트가 최대 토큰 수를 초과하여 청크로 분할 처리 (토큰 수: {len(tokenized_text)})")
            
            chunks = self._split_text(text, max_length)
            logger.debug(f"총 {len(chunks)}개 청크로 분할됨")
            
            # 각 청크 요약 - 각 청크를 2-3 문장으로 요약
            summaries = []
            chunk_min_length = min_sentences // 2 * token_per_sentence  # 더 짧게 설정
            chunk_max_length = max_sentences // 2 * token_per_sentence
            
            for i, chunk in enumerate(chunks):
                logger.debug(f"청크 {i+1}/{len(chunks)} 요약 중 (길이: {len(chunk)}자)")
                
                # 각 청크는 더 짧게 요약 (전체 요약이 3-5문장이 되도록)
                chunk_summary = self._summarize_single_chunk(
                    chunk, 
                    max_length=max_length,
                    min_output_length=chunk_min_length,
                    max_output_length=chunk_max_length,
                    num_beams=num_beams
                )
                summaries.append(chunk_summary)
            
            # 청크 요약 결합
            combined_summary = " ".join(summaries)
            
            # 결합된 요약이 너무 길면 다시 요약 (최종적으로 3-5 문장으로)
            if len(combined_summary.split('.')) > max_sentences + 1:  # 마침표 기준으로 문장 수 확인
                logger.debug("결합된 요약이 목표 문장 수를 초과하여 최종 요약 수행")
                final_summary = self._summarize_single_chunk(
                    combined_summary,
                    max_length=max_length,
                    min_output_length=fixed_min_length,
                    max_output_length=fixed_max_length,
                    num_beams=num_beams
                )
                
                result = {
                    "summary": final_summary,
                    "original_length": len(text),
                    "summary_length": len(final_summary),
                    "sentence_count": len(final_summary.split('.')) - 1  # 마지막 마침표 이후 빈 문자열 제외
                }
            else:
                result = {
                    "summary": combined_summary,
                    "original_length": len(text),
                    "summary_length": len(combined_summary),
                    "sentence_count": len(combined_summary.split('.')) - 1
                }
            
            self.total_summarized += 1
            self.total_time += time.time() - start_time
            
            return result
        
        # 단일 청크 처리
        summary = self._summarize_single_chunk(
            text, 
            max_length=max_length,
            min_output_length=fixed_min_length,
            max_output_length=fixed_max_length,
            num_beams=num_beams
        )
        
        # 문장 수 계산 (마침표 기준) 
        sentence_count = len(summary.split('.')) - 1
        
        result = {
            "summary": summary,
            "original_length": len(text),
            "summary_length": len(summary),
            "sentence_count": sentence_count
        }
        
        self.total_summarized += 1
        self.total_time += time.time() - start_time
        
        # 로그 출력 (500번째 분석마다)
        if self.total_summarized % 500 == 0:
            avg_time = self.total_time / self.total_summarized if self.total_summarized > 0 else 0
            logger.info(f"성능 통계 - 평균 요약 시간: {avg_time:.4f}초/텍스트, 총 요약 개수: {self.total_summarized}")
        
        return result
        
    def _summarize_single_chunk(self, text: str, max_length: int, min_output_length: int, max_output_length: int, num_beams: int) -> str:
        """단일 텍스트 청크 요약
        
        Args:
            text: 요약할 텍스트
            max_length: 입력 토큰 최대 길이
            min_output_length: 최소 출력 길이 (토큰)
            max_output_length: 최대 출력 길이 (토큰)
            num_beams: 빔 서치 크기
            
        Returns:
            요약 텍스트
        """
        # 입력 텍스트 토큰화
        inputs = self.tokenizer(
            text, 
            return_tensors="pt", 
            max_length=max_length, 
            truncation=True
        ).to(self.device)
        
        # 요약 생성
        with torch.no_grad():
            summary_ids = self.model.generate(
                inputs["input_ids"],
                num_beams=num_beams,
                max_length=max_output_length,
                min_length=min_output_length,
                length_penalty=1.5,  # 더 길고 완성도 높은 요약 선호 (기본 1.0)
                no_repeat_ngram_size=3,  # 반복 n-gram 방지 
                early_stopping=True,
                top_k=50,  # 상위 50개 토큰만 고려
                temperature=1.0  # 더 다양한 표현을 생성하도록 온도 설정
            )
        
        # 요약 텍스트 변환
        summary = self.tokenizer.decode(summary_ids[0], skip_special_tokens=True)
        return summary
    
    def summarize_batch(self, texts: List[str], batch_size: int = 16, max_length: int = 1024, summary_max_length: int = 128) -> List[Dict[str, Any]]:
        """여러 텍스트의 요약 수행
        
        Args:
            texts: 요약할 텍스트 리스트
            batch_size: 배치 크기
            max_length: 입력 토큰 최대 길이
            summary_max_length: 요약 결과 최대 길이 (0이면 원본 길이에 비례해서 계산)
            
        Returns:
            요약 결과 리스트
        """
        start_time = time.time()
        results = []
        
        for i in range(0, len(texts), batch_size):
            batch_texts = texts[i:i + batch_size]
            logger.debug(f"배치 요약 처리 중: {i+1}-{min(i+batch_size, len(texts))}/{len(texts)}")
            
            # 배치 텍스트별 개별 처리 (각 텍스트마다 길이가 다를 수 있으므로)
            batch_results = []
            for text in batch_texts:
                single_result = self.summarize(
                    text, 
                    max_length=max_length, 
                    summary_max_length=summary_max_length, 
                    num_beams=5
                )
                batch_results.append(single_result)
            
            results.extend(batch_results)
        
        batch_time = time.time() - start_time
        logger.info(f"배치 요약 완료: {len(texts)}개 텍스트, 소요시간: {batch_time:.2f}초 (평균: {batch_time/len(texts):.4f}초/텍스트)")
        
        self.total_summarized += len(texts)
        self.total_time += batch_time
        
        return results
    
    def _split_text(self, text: str, max_length: int = 1024) -> List[str]:
        """긴 텍스트를 여러 청크로 분할
        
        Args:
            text: 분할할 텍스트
            max_length: 최대 토큰 길이
            
        Returns:
            분할된 텍스트 리스트
        """
        words = text.split()
        chunks = []
        current_chunk = []
        current_length = 0
        
        for word in words:
            word_tokens = len(self.tokenizer.tokenize(word))
            if current_length + word_tokens > max_length:
                chunks.append(' '.join(current_chunk))
                current_chunk = [word]
                current_length = word_tokens
            else:
                current_chunk.append(word)
                current_length += word_tokens
        
        if current_chunk:
            chunks.append(' '.join(current_chunk))
        
        return chunks 