from typing import Dict

# 뉴스 카테고리 공통 설정
# Key: 영문 (API 경로, DB 저장 등에 사용), Value: 한글 (표시용)
SHARED_CATEGORIES: Dict[str, str] = {
    "economy": "경제",
    "business": "기업",
    "society": "사회",
    "world": "국제",
    "politics": "정치",
    "it": "IT",
    "culture": "문화"
}

# 여기에 다른 공통 설정 값들을 추가할 수 있습니다.
# 예를 들어, LOG_LEVEL 기본값 등
# DEFAULT_LOG_LEVEL: str = "INFO" 