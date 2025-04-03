"""
요약 프로세서 모듈 - KoBART 모델을 사용한 한국어 텍스트 요약

이 패키지는 KoBART 기반의 한국어 텍스트 요약 기능을 제공합니다.
뉴스 기사 등의 긴 텍스트를 효율적으로 요약하여 핵심 내용을 추출합니다.

주요 구성요소:
- summarizer.py: KoBART 기반 텍스트 요약 엔진
- processor.py: 요약 프로세서 및 MongoDB/Kafka 연동
- setup.py: 모델 다운로드 및 설정 도구
- run_processor.py: 요약 프로세서 실행 스크립트
"""

from .summarizer import TextSummarizer
from .processor import SummaryProcessor

__all__ = ['TextSummarizer', 'SummaryProcessor'] 