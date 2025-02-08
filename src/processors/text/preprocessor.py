from typing import List, Set
import re
from konlpy.tag import Mecab
import numpy as np

class TextPreprocessor:
    def __init__(self):
        self.mecab = Mecab()
        self._load_stopwords()
    
    def _load_stopwords(self):
        """기본 불용어 설정"""
        self.stopwords = {
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
            "아니다", "와", "오", "왜", "어째서", "무엇때문에", "어찌", "어떻해", "어떻게"
        }
    
    def preprocess(self, text: str) -> str:
        """텍스트 전처리 수행"""
        # 1. 특수문자 및 숫자 제거
        text = self._remove_special_characters(text)
        
        # 2. 불필요한 공백 제거
        text = self._normalize_spaces(text)
        
        return text
    
    def tokenize(self, text: str) -> List[str]:
        """텍스트를 형태소 단위로 분리"""
        # 형태소 분석
        morphs = self.mecab.pos(text)
        
        # 명사, 동사, 형용사만 선택 (NNG: 일반명사, NNP: 고유명사, VV: 동사, VA: 형용사)
        tokens = []
        for morph, pos in morphs:
            if pos.startswith(('NNG', 'NNP')) and len(morph) > 1:
                tokens.append(morph)
            elif pos.startswith(('VV', 'VA')):
                tokens.append(morph + '다')  # 동사, 형용사는 기본형으로 변환
        
        # 불용어 제거
        tokens = [token for token in tokens if token not in self.stopwords]
        
        return tokens
    
    def extract_keywords(self, text: str, top_n: int = 10) -> List[str]:
        """TF-IDF 기반 키워드 추출"""
        # 토큰화
        tokens = self.tokenize(text)
        
        # 단어 빈도 계산
        word_freq = {}
        for token in tokens:
            word_freq[token] = word_freq.get(token, 0) + 1
        
        # TF-IDF 계산 (여기서는 간단히 TF만 사용)
        keywords = sorted(word_freq.items(), key=lambda x: x[1], reverse=True)
        
        return [keyword for keyword, _ in keywords[:top_n]]
    
    @staticmethod
    def _remove_special_characters(text: str) -> str:
        """특수문자 및 숫자 제거"""
        text = re.sub(r'[^가-힣a-zA-Z\s]', ' ', text)
        return text
    
    @staticmethod
    def _normalize_spaces(text: str) -> str:
        """연속된 공백을 하나로 통일"""
        return ' '.join(text.split()) 