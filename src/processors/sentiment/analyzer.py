from typing import Dict, Any, List, Tuple
import torch
from transformers import AutoTokenizer, AutoModelForSequenceClassification
import numpy as np
from tqdm import tqdm
import os
import logging
import time

logger = logging.getLogger("sentiment-analyzer")

class SentimentAnalyzer:
    def __init__(self, model_name: str = "snunlp/KR-FinBert-SC", model_path: str = None):
        self.device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
        self.model_name = model_name
        
        logger.info(f"모델 로드 중 (디바이스: {self.device})")
        start_time = time.time()
        
        try:
            # 로컬 경로가 제공된 경우 해당 경로에서 로드
            if model_path:
                logger.info(f"로컬 모델 경로에서 로드: {model_path}")
                self.tokenizer = AutoTokenizer.from_pretrained(model_path)
                self.model = AutoModelForSequenceClassification.from_pretrained(model_path)
            else:
                # 아니면 Hugging Face에서 다운로드
                logger.info(f"Hugging Face에서 로드: {model_name}")
                self.tokenizer = AutoTokenizer.from_pretrained(model_name)
                self.model = AutoModelForSequenceClassification.from_pretrained(model_name)
            
            self.model.to(self.device)
            load_time = time.time() - start_time
            logger.info(f"모델 로드 완료 (소요시간: {load_time:.2f}초)")
            
            # 모델의 레이블 수 확인
            num_labels = self.model.config.num_labels
            logger.info(f"모델 레이블 수: {num_labels}")
            
        except Exception as e:
            logger.error(f"모델 로드 실패: {str(e)}")
            raise
        
        # KR-FinBert-SC는 금융 도메인 특화 감성분석 모델로 3개의 레이블을 사용합니다
        self.labels = ['negative', 'neutral', 'positive']
        
        # 성능 통계
        self.total_analyzed = 0
        self.total_time = 0
    
    def analyze(self, text: str, max_length: int = 512) -> Dict[str, Any]:
        """텍스트의 감정 분석
        
        Args:
            text: 분석할 텍스트
            max_length: 최대 토큰 길이
            
        Returns:
            감정 분석 결과를 담은 딕셔너리
        """
        start_time = time.time()
        
        # 입력 텍스트가 너무 길면 분할
        if len(text) > max_length * 4:  # 대략적인 추정치
            chunks = self._split_text(text, max_length)
            if len(chunks) > 1:
                logger.debug(f"텍스트가 길어서 {len(chunks)}개 청크로 분할됨")
                # 청크별로 분석 후 평균 점수 계산
                results = [self.analyze(chunk) for chunk in chunks]
                avg_scores = {
                    label: sum(r['scores'][label] for r in results) / len(results)
                    for label in self.labels
                }
                predicted_label = self.labels[np.argmax([avg_scores[label] for label in self.labels])]
                
                self.total_analyzed += 1
                self.total_time += time.time() - start_time
                
                return {
                    "sentiment": predicted_label,
                    "scores": avg_scores
                }
        
        # 입력 텍스트 토큰화
        inputs = self.tokenizer(
            text,
            return_tensors="pt",
            truncation=True,
            max_length=max_length,
            padding=True
        ).to(self.device)
        
        # 모델 추론
        with torch.no_grad():
            outputs = self.model(**inputs)
            predictions = torch.softmax(outputs.logits, dim=-1)
            
        # 결과 처리
        sentiment_scores = predictions[0].cpu().numpy()
        
        # 모델 출력이 레이블 수와 일치하는지 확인
        if len(sentiment_scores) != len(self.labels):
            logger.warning(f"모델 출력 크기({len(sentiment_scores)})가 레이블 수({len(self.labels)})와 일치하지 않습니다!")
        
        predicted_idx = np.argmax(sentiment_scores)
        predicted_label = self.labels[predicted_idx] if predicted_idx < len(self.labels) else "unknown"
        
        self.total_analyzed += 1
        self.total_time += time.time() - start_time
        
        # 로그 출력 (500번째 분석마다)
        if self.total_analyzed % 500 == 0:
            avg_time = self.total_time / self.total_analyzed if self.total_analyzed > 0 else 0
            logger.info(f"성능 통계 - 평균 분석 시간: {avg_time:.4f}초/텍스트, 총 분석 개수: {self.total_analyzed}")
        
        return {
            "sentiment": predicted_label,
            "scores": {
                label: float(score)
                for label, score in zip(self.labels, sentiment_scores)
            }
        }
    
    def analyze_batch(self, texts: List[str], batch_size: int = 32) -> List[Dict[str, Any]]:
        """여러 텍스트의 감정 분석
        
        Args:
            texts: 분석할 텍스트 리스트
            batch_size: 배치 크기
            
        Returns:
            감정 분석 결과 리스트
        """
        start_time = time.time()
        results = []
        
        for i in tqdm(range(0, len(texts), batch_size), desc="배치 처리"):
            batch_texts = texts[i:i + batch_size]
            
            # 배치 토큰화
            inputs = self.tokenizer(
                batch_texts,
                return_tensors="pt",
                truncation=True,
                max_length=512,
                padding=True
            ).to(self.device)
            
            # 배치 추론
            with torch.no_grad():
                outputs = self.model(**inputs)
                predictions = torch.softmax(outputs.logits, dim=-1)
            
            # 배치 결과 처리
            batch_scores = predictions.cpu().numpy()
            for scores in batch_scores:
                predicted_idx = np.argmax(scores)
                predicted_label = self.labels[predicted_idx] if predicted_idx < len(self.labels) else "unknown"
                
                results.append({
                    "sentiment": predicted_label,
                    "scores": {
                        label: float(score)
                        for label, score in zip(self.labels, scores)
                    }
                })
        
        batch_time = time.time() - start_time
        logger.info(f"배치 처리 완료: {len(texts)}개 텍스트, 소요시간: {batch_time:.2f}초 (평균: {batch_time/len(texts):.4f}초/텍스트)")
        
        self.total_analyzed += len(texts)
        self.total_time += batch_time
        
        return results
    
    def get_sentiment_keywords(self, text: str, tokenized_words: List[str]) -> Dict[str, List[str]]:
        """감정별 주요 키워드 추출
        
        Args:
            text: 원본 텍스트
            tokenized_words: 토큰화된 단어 리스트
            
        Returns:
            감정별 키워드 딕셔너리
        """
        keyword_sentiments = {
            'positive': [],
            'neutral': [],
            'negative': []
        }
        
        # 각 단어별 감정 분석 (단어 빈도가 높은 상위 단어만 분석)
        word_freq = {}
        for word in tokenized_words:
            if len(word) < 2:  # 짧은 단어 무시
                continue
            word_freq[word] = word_freq.get(word, 0) + 1
        
        # 빈도 순으로 정렬하여 상위 단어만 분석
        top_words = sorted(word_freq.items(), key=lambda x: x[1], reverse=True)[:30]
        top_word_list = [word for word, _ in top_words]
        
        if not top_word_list:
            return keyword_sentiments
            
        logger.info(f"상위 {len(top_word_list)}개 단어에 대해 배치 감정 분석 수행")
        
        # 배치 처리로 한 번에 분석 (성능 개선)
        batch_results = self.analyze_batch(top_word_list)
        
        # 결과를 감정별로 분류
        for word, result in zip(top_word_list, batch_results):
            label = result['sentiment']
            score = result['scores'][label]
            
            if score > 0.6:  # 확실한 감정을 가진 단어만 선택
                keyword_sentiments[label].append(word)
        
        return keyword_sentiments
    
    def _split_text(self, text: str, max_length: int = 512) -> List[str]:
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