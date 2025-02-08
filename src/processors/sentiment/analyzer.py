from typing import Dict, Any, List, Tuple
import torch
from transformers import AutoTokenizer, AutoModelForSequenceClassification
import numpy as np
from tqdm import tqdm
import os

class SentimentAnalyzer:
    def __init__(self, model_name: str = "beomi/KcELECTRA-base-v2022"):
        self.device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
        self.model_name = model_name
        
        # 토크나이저와 모델 로드
        self.tokenizer = AutoTokenizer.from_pretrained(model_name)
        self.model = AutoModelForSequenceClassification.from_pretrained(model_name, num_labels=3)
        self.model.to(self.device)
        
        # 감정 레이블
        self.labels = ['negative', 'neutral', 'positive']
    
    def analyze(self, text: str, max_length: int = 512) -> Dict[str, Any]:
        """텍스트의 감정 분석"""
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
        predicted_label = self.labels[np.argmax(sentiment_scores)]
        
        return {
            "sentiment": predicted_label,
            "scores": {
                label: float(score)
                for label, score in zip(self.labels, sentiment_scores)
            }
        }
    
    def analyze_batch(self, texts: List[str], batch_size: int = 32) -> List[Dict[str, Any]]:
        """여러 텍스트의 감정 분석"""
        results = []
        
        for i in tqdm(range(0, len(texts), batch_size)):
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
                predicted_label = self.labels[np.argmax(scores)]
                results.append({
                    "sentiment": predicted_label,
                    "scores": {
                        label: float(score)
                        for label, score in zip(self.labels, scores)
                    }
                })
        
        return results
    
    def get_sentiment_keywords(self, text: str, tokenized_words: List[str]) -> Dict[str, List[str]]:
        """감정별 주요 키워드 추출"""
        keyword_sentiments = {
            'positive': [],
            'negative': [],
            'neutral': []
        }
        
        # 각 단어별 감정 분석
        for word in tokenized_words:
            if len(word) < 2:  # 짧은 단어 무시
                continue
                
            sentiment = self.analyze(word)
            label = sentiment['sentiment']
            score = sentiment['scores'][label]
            
            if score > 0.6:  # 확실한 감정을 가진 단어만 선택
                keyword_sentiments[label].append(word)
        
        return keyword_sentiments
    
    def _split_text(self, text: str, max_length: int = 512) -> List[str]:
        """긴 텍스트를 여러 청크로 분할"""
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