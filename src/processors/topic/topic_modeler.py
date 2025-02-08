from typing import List, Dict, Any
import numpy as np
from sklearn.feature_extraction.text import CountVectorizer
from sklearn.decomposition import LatentDirichletAllocation
from collections import defaultdict
import joblib
import os

from ..text.preprocessor import TextPreprocessor

class TopicModeler:
    def __init__(self, n_topics: int = 10, max_iter: int = 10):
        self.n_topics = n_topics
        self.max_iter = max_iter
        self.preprocessor = TextPreprocessor()
        
        # 모델 초기화
        self.vectorizer = CountVectorizer(max_df=0.95, min_df=2, max_features=1000)
        self.lda = LatentDirichletAllocation(
            n_components=n_topics,
            max_iter=max_iter,
            learning_method='batch',
            random_state=42
        )
        
        self.model_path = "models/topic_model"
        self.vectorizer_path = "models/vectorizer"
        
        # 모델 디렉토리 생성
        os.makedirs("models", exist_ok=True)
    
    def fit(self, texts: List[str]):
        """토픽 모델 학습"""
        # 텍스트 전처리
        processed_texts = [self.preprocessor.preprocess(text) for text in texts]
        
        # DTM (Document-Term Matrix) 생성
        dtm = self.vectorizer.fit_transform(processed_texts)
        
        # LDA 모델 학습
        self.lda.fit(dtm)
        
        # 모델 저장
        self._save_model()
    
    def transform(self, text: str) -> Dict[str, Any]:
        """텍스트의 토픽 분포 예측"""
        # 텍스트 전처리
        processed_text = self.preprocessor.preprocess(text)
        
        # DTM 변환
        dtm = self.vectorizer.transform([processed_text])
        
        # 토픽 분포 예측
        topic_dist = self.lda.transform(dtm)[0]
        
        # 주요 토픽 추출
        main_topics = self._get_main_topics(topic_dist)
        
        return {
            "topic_distribution": topic_dist.tolist(),
            "main_topics": main_topics,
            "topic_keywords": self.get_topic_keywords()
        }
    
    def get_topic_keywords(self, top_n: int = 10) -> List[List[str]]:
        """각 토픽별 주요 키워드 추출"""
        feature_names = self.vectorizer.get_feature_names_out()
        keywords = []
        
        for topic_idx, topic in enumerate(self.lda.components_):
            top_keywords_idx = topic.argsort()[:-top_n-1:-1]
            top_keywords = [feature_names[i] for i in top_keywords_idx]
            keywords.append(top_keywords)
        
        return keywords
    
    def _get_main_topics(self, topic_dist: np.ndarray, threshold: float = 0.1) -> List[int]:
        """주요 토픽 추출 (임계값 이상의 확률을 가진 토픽)"""
        return [idx for idx, prob in enumerate(topic_dist) if prob > threshold]
    
    def _save_model(self):
        """모델 저장"""
        joblib.dump(self.lda, self.model_path)
        joblib.dump(self.vectorizer, self.vectorizer_path)
    
    def load_model(self):
        """저장된 모델 로드"""
        if os.path.exists(self.model_path) and os.path.exists(self.vectorizer_path):
            self.lda = joblib.load(self.model_path)
            self.vectorizer = joblib.load(self.vectorizer_path)
            return True
        return False 