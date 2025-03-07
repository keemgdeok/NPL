from typing import List, Dict, Any, Optional, Union, Tuple
import os
import numpy as np
from bertopic import BERTopic
from sklearn.feature_extraction.text import CountVectorizer, TfidfVectorizer
from sentence_transformers import SentenceTransformer
import logging
from umap import UMAP
from hdbscan import HDBSCAN
import torch
from pathlib import Path
import warnings

# 불필요한 경고 비활성화
warnings.filterwarnings("ignore", category=UserWarning)

logger = logging.getLogger(__name__)

class KoreanTopicModeler:
    """한국어 뉴스를 위한 BERTopic 기반 토픽 모델링 클래스"""
    
    def __init__(
        self,
        n_topics: int = 10,
        embedding_model: Any = None,
        calculate_probabilities: bool = True,
        model_path: str = "models/korean_news_topics"
    ):
        """
        Args:
            n_topics: 추출할 토픽 수
            embedding_model: 임베딩 모델 (기본값: CountVectorizer)
            calculate_probabilities: 토픽 확률 계산 여부
            model_path: 모델 저장 경로
        """
        self.n_topics = n_topics
        self.model_path = model_path
        self._model = None
        
        # 모델 초기화 또는 로드
        loaded = self.load_model()
        if not loaded:
            self._initialize_model(embedding_model, calculate_probabilities)
    
    def _initialize_model(self, embedding_model=None, calculate_probabilities=True):
        """BERTopic 모델 초기화"""
        logger.info("새 BERTopic 모델을 초기화합니다.")
        
        # 한국어 불용어 설정
        korean_stopwords = [
            "있다", "하다", "이다", "되다", "않다", "없다", "같다", "보다", "이", "그", "저",
            "것", "수", "등", "들", "및", "에서", "그리고", "또는", "또한", "한", "할", "수",
            "이런", "저런", "그런", "아", "휴", "아이구", "아이쿠", "아이고", "어", "나", "우리",
            "저희", "따라", "의해", "을", "를", "에", "의", "가", "으로", "로", "에게", "뿐이다",
            "의거하여", "근거하여", "입각하여", "기준으로", "예하면", "예를", "들면", "들자면",
            "저것만", "소인", "소생", "저희", "지말고", "하지마", "하지마라", "다른", "물론",
            "또한", "그리고", "비길수", "없다", "해서는", "안된다", "뿐만", "아니라", "만이",
            "아니다", "만은", "막론하고", "관계없이", "그치지", "않다", "그러나", "그런데",
            "하지만", "든간에", "논하지", "않다", "따지지", "않다", "설사", "비록", "더라도",
            "아니면", "만", "못하다", "하는", "편이", "낫다", "불문하고", "향하여", "향해서",
            "향하다", "쪽으로", "틈타", "이용하여", "타다", "오르다", "제외하고", "이외에",
            "이", "밖에", "하여야", "비로소", "한다면", "몰라도", "외에도", "이곳", "여기",
            "부터", "기점으로", "따라서", "할", "생각이다", "하려고하다", "이리하여", "그리하여",
            "그렇게", "함으로써", "하지만", "일때", "할때", "앞에서", "중에서", "보는데서",
            "으로써", "로써", "까지", "해야한다", "일것이다", "반드시", "할줄알다", "할수있다",
            "할수있어", "임에", "틀림없다", "한다면", "등", "등등", "제", "겨우", "단지",
            "다만", "할뿐", "딩동", "댕그", "대해서", "대하여", "대하면", "훨씬", "얼마나",
            "얼마만큼", "얼마큼", "남짓", "여", "얼마간", "약간", "다소", "좀", "조금",
            "다수", "몇", "얼마", "지만", "하물며", "또한", "그러나", "그렇지만", "하지만",
            "이외에도", "대해", "말하자면", "뿐이다", "다음에", "반대로", "반대로", "말하자면",
            "이와", "반대로", "바꾸어서", "말하면", "바꾸어서", "한다면", "만약", "그렇지않으면",
            "까악", "툭", "딱", "삐걱거리다", "보드득", "비걱거리다", "꽈당", "응당", "해야한다",
            "에", "가서", "각", "각각", "여러분", "각종", "각자", "제각기", "하도록하다",
            "그러므로", "그래서", "고로", "한", "까닭에", "하기", "때문에", "거니와", "이지만",
            "대하여", "관하여", "관한", "과연", "실로", "아니나다를가", "생각한대로", "진짜로",
            "한적이있다", "하곤하였다", "하", "하하", "허허", "아하", "거바", "와", "오",
            "왜", "어째서", "무엇때문에", "어찌", "하겠는가", "무슨", "어디", "어느곳",
            "더군다나", "하물며", "더욱이는", "어느때", "언제", "야", "이봐", "어이", "여보시오",
            "흐흐", "흥", "휴", "헉헉", "헐떡헐떡", "영차", "여차", "어기여차", "끙끙",
            "아야", "앗", "아야", "콸콸", "졸졸", "좍좍", "뚝뚝", "주룩주룩", "솨", "우르르",
            "그래도", "또", "그리고", "바꾸어말하면", "바꾸어말하자면", "혹은", "혹시", "답다",
            "및", "그에", "따르는", "때가", "되어", "즉", "지든지", "설령", "가령", "하더라도",
            "할지라도", "일지라도", "지든지", "몇", "거의", "하마터면", "인젠", "이젠", "된바에야",
            "된이상", "만큼", "어찌됏든", "그위에", "게다가", "점에서", "보아", "비추어", "보아",
            "아니다", "와", "오", "왜", "어째서", "무엇때문에", "어찌", "어떻해", "어떻게",
            
            # 뉴스 관련 일반 용어
            "기자", "보도", "취재", "소식", "뉴스", "기사", "헤드라인", "특종", "속보",
            "단독", "보도에", "따르면", "인터뷰", "발표", "관계자", "공식", "비공식", "논평",
            "해명", "입장", "반응", "경향", "신문", "방송", "매체", "언론", "팩트", "출처",
            
            # 시간 관련 표현
            "어제", "오늘", "내일", "모레", "그저께", "최근", "지난", "이번", "다음", "당시",
            "현재", "미래", "올해", "작년", "내년", "지난해", "다음해", "이달", "저번달", "다음달",
            "이번주", "저번주", "다음주", "오전", "오후", "새벽", "저녁", "밤", "주말", "평일",
            
            # 자주 사용되는 부사
            "매우", "아주", "너무", "다시", "계속", "이미", "거의", "바로", "단지", "특히",
            "주로", "항상", "자주", "대체로", "일부", "일단", "우선", "결국", "반드시", "꼭",
            "정말", "실제", "가장", "제일", "더욱", "대략", "약", "대체", "전혀", "결코",
            
            # 뉴스 인용 관련
            "말했다", "전했다", "밝혔다", "강조했다", "설명했다", "언급했다", "주장했다", "덧붙였다",
            "밝혀졌다", "알려졌다", "보도했다", "확인했다", "부인했다", "반박했다", "지적했다",
            "강조한", "말한", "밝힌", "전한", "언급한", "이라며", "라고", "이라고", "하면서",
            
            # 뉴스에 자주 등장하는 형식적 표현
            "관련하여", "따르면", "의하면", "결과", "관련", "가능성", "예정", "방침", "전망",
            "계획", "상황", "사실", "내용", "이유", "의견", "필요", "대책", "예상", "분석",
            "조사", "연구", "평가", "판단", "주장", "사례", "경우", "원인", "고려", "검토"
            ]
        
        # 임베딩 모델 설정
        if embedding_model is None:
            logger.info("CountVectorizer를 임베딩 모델로 사용합니다.")
            # embedding_model = CountVectorizer(
            #     stop_words=korean_stopwords,
            #     ngram_range=(1, 2),
            #     max_features=10000,
            #     max_df=0.95,
            #     min_df=5
            # )
            embedding_model = SentenceTransformer('jhgan/ko-sbert-nli')
        
        # UMAP 설정 - CPU 최적화
        umap_model = UMAP(
            n_neighbors=15,
            n_components=5,
            min_dist=0.0,
            metric='cosine',
            random_state=42,
            low_memory=False,
            n_jobs=4  # CPU 코어 수에 맞게 조정
        )
        
        # HDBSCAN 설정
        hdbscan_model = HDBSCAN(
            min_cluster_size=5,
            min_samples=2,
            metric='euclidean',
            prediction_data=True,
            core_dist_n_jobs=4  # CPU 코어 수에 맞게 조정
        )
        
        # BERTopic 모델 초기화
        self._model = BERTopic(
            embedding_model=embedding_model,
            umap_model=umap_model,
            hdbscan_model=hdbscan_model,
            language="korean",
            nr_topics=self.n_topics,
            min_topic_size=5,
            verbose=True,
            calculate_probabilities=calculate_probabilities,
            top_n_words=20  # 토픽당 더 많은 단어 저장
        )
    
    def fit(self, texts: List[str]):
        """모델 학습
        
        Args:
            texts: 학습할 텍스트 목록
        
        Returns:
            (topics, probs): 각 문서의 토픽 ID와 확률 분포
        """
        if len(texts) < 10:
            logger.warning(f"학습 데이터가 너무 적습니다: {len(texts)}개")
            return None, None
            
        try:
            # 데이터 크기에 따라 배치 처리 여부 결정
            batch_size = 1000
            
            if len(texts) > batch_size:
                return self._fit_large_dataset(texts, batch_size)
            else:
                # 단일 배치로 학습
                topics, probs = self._model.fit_transform(texts)
                self._reduce_topics_if_needed(topics)
                self._generate_topic_labels()
                self.save_model()
                return topics, probs
                
        except Exception as e:
            logger.error(f"모델 학습 중 오류 발생: {str(e)}")
            return None, None
    
    def _fit_large_dataset(self, texts: List[str], batch_size: int):
        """대용량 데이터셋 배치 처리
        
        Args:
            texts: 텍스트 목록
            batch_size: 배치 크기
        
        Returns:
            (topics, probs): 토픽 및 확률
        """
        logger.info(f"대용량 데이터 ({len(texts)}개)를 배치 처리합니다.")
        
        all_topics = []
        all_probs = []
        
        # 배치 단위로 학습
        for i in range(0, len(texts), batch_size):
            batch_texts = texts[i:i+batch_size]
            logger.info(f"배치 처리 중: {i}~{i+len(batch_texts)} / {len(texts)}")
            
            if i == 0:  # 첫 배치는 학습
                topics, probs = self._model.fit_transform(batch_texts)
            else:  # 나머지는 변환
                batch_topics, batch_probs = self._model.transform(batch_texts)
                
            # 결과 모으기
            if i == 0:
                all_topics = topics
                all_probs = probs
            else:
                all_topics.extend(batch_topics)
                all_probs.extend(batch_probs)
        
        # 모델 최적화 및 저장
        self._reduce_topics_if_needed(all_topics)
        self._generate_topic_labels()
        self.save_model()
        
        return all_topics, all_probs
    
    def transform(self, text: str) -> Dict[str, Any]:
        """단일 텍스트에 대한 토픽 예측
        
        Args:
            text: 처리할 텍스트
            
        Returns:
            토픽 분석 결과
        """
        try:
            # 단일 문서를 리스트로 변환하여 처리
            topic, prob = self._model.transform([text])
            
            # 토픽 정보 조회
            topic_id = topic[0]  # 첫 번째 (유일한) 문서의 토픽
            
            # 토픽 키워드 추출
            topic_keywords = self.get_topic_keywords()
            
            # 결과 반환
            return {
                "topic_id": int(topic_id),
                "topic_prob": float(prob[0][topic_id]) if len(prob) > 0 and topic_id in prob[0] else 0.0,
                "topic_keywords": topic_keywords,
                "topic_distribution": prob[0].tolist() if len(prob) > 0 else [],
                "topic_label": self._model.topic_labels_.get(topic_id, f"토픽 {topic_id}") if hasattr(self._model, 'topic_labels_') else f"토픽 {topic_id}"
            }
        
        except Exception as e:
            # logger.error(f"토픽 분석 중 오류 발생: {str(e)}")
            return {
                "topic_id": -1,
                "topic_prob": 0.0,
                "topic_keywords": [["오류", "발생"]],
                "topic_distribution": [],
                "topic_label": "오류"
            }
    
    def get_topic_keywords(self, top_n: int = 10) -> List[List[str]]:
        """각 토픽별 주요 키워드 조회
        
        Args:
            top_n: 각 토픽별 상위 키워드 수
            
        Returns:
            토픽별 키워드 목록
        """
        topics = self._model.get_topics()
        return [
            [word for word, _ in topics.get(topic_id, [])[:top_n]] 
            for topic_id in range(len(topics))
        ]
    
    def _reduce_topics_if_needed(self, topics):
        """필요한 경우 토픽 수 줄이기"""
        if topics is None:
            return
            
        # 토픽 정보 확인
        topic_info = self._model.get_topic_info()
        
        # 토픽이 너무 많거나 대부분이 -1 (노이즈)인 경우 처리
        if len(topic_info) > self.n_topics * 2 or (-1 in topics and topics.count(-1) > len(topics) * 0.5):
            try:
                logger.info(f"토픽 수 감소 시도 (현재 토픽 수: {len(topic_info)}, 목표: {self.n_topics})")
                self._model.reduce_topics(topics, self.n_topics)
                logger.info("토픽 수 감소 완료")
            except Exception as e:
                logger.error(f"토픽 수 감소 실패: {str(e)}")
    
    def _generate_topic_labels(self):
        """토픽 자동 라벨링"""
        try:
            topic_labels = self._model.generate_topic_labels(nr_words=3, topic_prefix=False)
            self._model.set_topic_labels(topic_labels)
            logger.info("토픽 라벨 생성 완료")
        except Exception as e:
            logger.warning(f"토픽 라벨 생성 실패: {str(e)}")
    
    def save_model(self, path: str = None, serialization: str = "safetensors"):
        """모델 저장
        
        Args:
            path: 저장 경로 (None인 경우 기본 경로 사용)
            serialization: 직렬화 방식 ('pickle' 또는 'safetensors')
        """
        try:
            # 경로 설정
            save_path = path or self.model_path
            
            # 경로가 존재하지 않으면 생성
            # os.makedirs(os.path.dirname(save_path), exist_ok=True)
            
            # 모델 저장
            self._model.save(save_path, serialization='safetensors')
            logger.info(f"모델을 {save_path}에 저장했습니다.")
            return True
        except Exception as e:
            logger.error(f"모델 저장 실패: {str(e)}")
            
            # 백업 경로에 저장 시도
            try:
                backup_path = "models/backup_korean_news_topics"
                os.makedirs(os.path.dirname(backup_path), exist_ok=True)
                self._model.save(backup_path, serialization="pickle")
                logger.info(f"모델을 백업 경로 {backup_path}에 저장했습니다.")
                return True
            except Exception as backup_error:
                logger.error(f"백업 저장도 실패: {str(backup_error)}")
                return False
    
    def load_model(self, path: str = None):
        """저장된 모델 불러오기
        
        Args:
            path: 모델 경로 (None인 경우 기본 경로 사용)
            serialization: 직렬화 방식 ('pickle' 또는 'safetensors')
            
        Returns:
            로드 성공 여부
        """
        try:
            # 경로 설정
            load_path = path or self.model_path
            
            # 경로가 존재하는지 확인
            if not os.path.exists(load_path):
                logger.warning(f"모델 경로가 존재하지 않습니다: {load_path}")
                return False
                
            # 모델 로딩
            self._model = BERTopic.load(load_path)
            logger.info(f"모델을 {load_path}에서 불러왔습니다.")
            return True
        
        except Exception as e:
            logger.error(f"모델 로딩 실패: {str(e)}")
            
 
    
    # 주제 요약 관련 메서드
    def summarize_topics(self, docs: List[str] = None, top_n: int = 5):
        """주제 요약 정보 생성
        
        Args:
            docs: 요약할 문서 목록 (없으면 기존 학습된 모델 사용)
            top_n: 각 토픽별 상위 키워드 수
            
        Returns:
            주제 요약 정보
        """
        # 새 문서가 제공된 경우 변환
        if docs:
            topics, _ = self._model.transform(docs)
        else:
            topics = None
            
        # 토픽 정보 얻기
        topic_info = self._model.get_topic_info()
        
        # 토픽별 요약 정보 생성
        summaries = []
        
        for idx, row in topic_info.iterrows():
            topic_id = row['Topic']
            if topic_id == -1:  # 아웃라이어 토픽 건너뛰기
                continue
                
            # 토픽 키워드 가져오기
            keywords = [word for word, _ in self._model.get_topic(topic_id)[:top_n]]
            
            # 토픽 라벨 가져오기
            if hasattr(self._model, 'topic_labels_'):
                label = self._model.topic_labels_.get(topic_id, f"토픽 {topic_id}")
            else:
                label = f"토픽 {topic_id}"
            
            # 토픽 크기 (문서 수)
            size = row['Count']
            
            # 대표 문서 가져오기
            try:
                representative_docs = self._model.get_representative_docs(topic_id)
            except:
                representative_docs = []
            
            summaries.append({
                "id": int(topic_id),
                "label": label,
                "keywords": keywords,
                "size": int(size),
                "representative_docs": representative_docs[:3] if representative_docs else []
            })
        
        return {
            "total_topics": len(summaries),
            "topics": summaries
        }
    
    # 중요 메서드만 BERTopic에서 직접 노출
    def get_topic_info(self):
        """전체 토픽 정보 조회"""
        return self._model.get_topic_info()
    
    def get_topic(self, topic_id):
        """특정 토픽의 키워드 조회"""
        return self._model.get_topic(topic_id)
    
    def get_topics(self):
        """모든 토픽 정보 조회"""
        return self._model.get_topics()
    
    def get_topic_freq(self):
        """토픽 빈도 조회"""
        return self._model.get_topic_freq()
    
    def get_document_info(self, docs):
        """문서별 토픽 정보 조회"""
        return self._model.get_document_info(docs) 