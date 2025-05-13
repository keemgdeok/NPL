import os
import streamlit as st
from datetime import datetime, timedelta
import pandas as pd
from typing import Dict, Any, Optional, List, Union
import re

# API 설정
API_URL = os.getenv("API_URL", "http://localhost:8000/api/v1")

# 감성 맵핑 정보
SENTIMENT_MAP = {
    "positive": {
        "emoji": "😀",
        "color": "#4CAF50",  # 녹색
        "label": "긍정"
    },
    "neutral": {
        "emoji": "😐",
        "color": "#607D8B",  # 회색
        "label": "중립"
    },
    "negative": {
        "emoji": "😞",
        "color": "#F44336",  # 빨간색
        "label": "부정"
    }
}

def format_datetime(dt_str: Optional[str] = None, format_str: str = "%Y년 %m월 %d일 %H:%M") -> str:
    """
    날짜/시간 문자열을 포맷팅합니다.
    
    Args:
        dt_str: ISO 형식의 날짜/시간 문자열 또는 None
        format_str: 포맷 문자열
        
    Returns:
        포맷팅된 날짜/시간 문자열
    """
    if not dt_str:
        return "날짜 없음"
    
    try:
        # ISO 형식 문자열을 datetime 객체로 변환
        dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        return dt.strftime(format_str)
    except (ValueError, TypeError):
        return "잘못된 날짜 형식"

def format_text(text: Optional[str], max_length: int = 200, add_ellipsis: bool = True) -> str:
    """
    텍스트를 특정 길이로 자르고 필요시 말줄임표를 추가합니다.
    
    Args:
        text: 원본 텍스트
        max_length: 최대 길이
        add_ellipsis: 말줄임표 추가 여부
        
    Returns:
        포맷팅된 텍스트
    """
    if not text:
        return ""
    
    # HTML 태그 제거
    clean_text = re.sub(r'<.*?>', '', text)
    
    # 텍스트가 최대 길이보다 길면 자르기
    if len(clean_text) > max_length:
        if add_ellipsis:
            return clean_text[:max_length] + "..."
        return clean_text[:max_length]
    
    return clean_text

def get_sentiment_emoji(sentiment: str) -> str:
    """
    감성에 해당하는 이모지를 반환합니다.
    
    Args:
        sentiment: 감성 레이블 (positive, neutral, negative)
        
    Returns:
        감성 이모지
    """
    sentiment_info = SENTIMENT_MAP.get(sentiment, {})
    return sentiment_info.get("emoji", "❓")

def get_sentiment_color(sentiment: str) -> str:
    """
    감성에 해당하는 색상 코드를 반환합니다.
    
    Args:
        sentiment: 감성 레이블 (positive, neutral, negative)
        
    Returns:
        색상 코드
    """
    sentiment_info = SENTIMENT_MAP.get(sentiment, {})
    return sentiment_info.get("color", "#9E9E9E")

def get_sentiment_label(sentiment: str) -> str:
    """
    감성에 해당하는 한글 레이블을 반환합니다.
    
    Args:
        sentiment: 감성 레이블 (positive, neutral, negative)
        
    Returns:
        한글 감성 레이블
    """
    sentiment_info = SENTIMENT_MAP.get(sentiment, {})
    return sentiment_info.get("label", "알 수 없음")

def init_session_state(**kwargs):
    """
    세션 상태를 초기화합니다.
    
    Args:
        **kwargs: 초기화할 세션 상태 변수들
    """
    # 기본 세션 상태 변수들
    default_states = {
        "search_query": "",
        "selected_category": "전체",
        "date_range": 30,
        "view_mode": "list",
        "sentiment_filter": "전체",
        "page_number": 1,
        "items_per_page": 10
    }
    
    # 기본값과 사용자 제공 값을 병합
    states = {**default_states, **kwargs}
    
    # 세션 상태 설정
    for key, value in states.items():
        if key not in st.session_state:
            st.session_state[key] = value

def get_readable_number(number: Union[int, float], precision: int = 1) -> str:
    """
    숫자를 읽기 쉽게 변환합니다.
    
    Args:
        number: 원본 숫자
        precision: 소수점 자릿수
        
    Returns:
        변환된, 읽기 쉬운 숫자 문자열
    """
    if number is None:
        return "0"
    
    # 0 처리
    if number == 0:
        return "0"
    
    # 음수 처리
    sign = ""
    if number < 0:
        sign = "-"
        number = abs(number)
    
    # 큰 숫자 처리
    suffixes = ["", "K", "M", "B", "T"]
    suffix_idx = 0
    
    while number >= 1000 and suffix_idx < len(suffixes) - 1:
        number /= 1000
        suffix_idx += 1
    
    # 소수점 제거가 가능한 경우 처리
    if number == int(number):
        formatted = str(int(number))
    else:
        formatted = f"{number:.{precision}f}"
        # 끝의 0 제거
        formatted = formatted.rstrip("0").rstrip("." if formatted.endswith(".") else "")
    
    return f"{sign}{formatted}{suffixes[suffix_idx]}"

def paginate_dataframe(df: pd.DataFrame, page: int, items_per_page: int) -> pd.DataFrame:
    """
    데이터프레임을 페이지네이션합니다.
    
    Args:
        df: 원본 데이터프레임
        page: 페이지 번호 (1부터 시작)
        items_per_page: 페이지당 항목 수
        
    Returns:
        페이지네이션된 데이터프레임
    """
    if df.empty:
        return df
    
    # 인덱스 계산
    start_idx = (page - 1) * items_per_page
    end_idx = start_idx + items_per_page
    
    # 유효한 범위 확인
    total_rows = len(df)
    if start_idx >= total_rows:
        start_idx = max(0, total_rows - items_per_page)
        end_idx = total_rows
    
    # 페이지 데이터 반환
    return df.iloc[start_idx:end_idx].copy()

def create_pagination_ui(total_items: int, page: int, items_per_page: int, key_prefix: str = "pagination") -> int:
    """
    페이지네이션 UI를 생성합니다.
    
    Args:
        total_items: 전체 항목 수
        page: 현재 페이지 번호
        items_per_page: 페이지당 항목 수
        key_prefix: 위젯 키 접두사
        
    Returns:
        선택된 페이지 번호
    """
    if total_items <= 0 or items_per_page <= 0:
        return 1
    
    # 전체 페이지 수 계산
    total_pages = (total_items + items_per_page - 1) // items_per_page
    
    # 페이지가 범위를 벗어나면 조정
    page = max(1, min(page, total_pages))
    
    # 페이지네이션 UI가 필요 없는 경우
    if total_pages <= 1:
        return 1
    
    # 네비게이션 컨트롤 설정
    st.markdown(f"**{total_items}개 항목 중 {(page - 1) * items_per_page + 1}-{min(page * items_per_page, total_items)}개 표시**")
    
    col1, col2, col3 = st.columns([1, 3, 1])
    
    # 이전 페이지 버튼
    with col1:
        if page > 1:
            if st.button("◀ 이전", key=f"{key_prefix}_prev"):
                return page - 1
    
    # 페이지 선택기
    with col2:
        # 페이지 범위 계산 (최대 7개 페이지 표시)
        max_visible = 7
        half_visible = max_visible // 2
        
        if total_pages <= max_visible:
            # 모든 페이지 표시
            page_range = range(1, total_pages + 1)
        else:
            # 현재 페이지 주변 페이지만 표시
            start_page = max(1, page - half_visible)
            end_page = min(total_pages, start_page + max_visible - 1)
            
            # 범위 조정
            if end_page - start_page < max_visible - 1:
                start_page = max(1, end_page - max_visible + 1)
            
            page_range = range(start_page, end_page + 1)
        
        # 페이지 버튼 표시
        cols = st.columns(len(page_range))
        
        for i, p in enumerate(page_range):
            with cols[i]:
                if p == page:
                    st.markdown(f"<div style='text-align: center; font-weight: bold;'>{p}</div>", unsafe_allow_html=True)
                else:
                    if st.button(str(p), key=f"{key_prefix}_page_{p}"):
                        return p
    
    # 다음 페이지 버튼
    with col3:
        if page < total_pages:
            if st.button("다음 ▶", key=f"{key_prefix}_next"):
                return page + 1
    
    return page

def get_time_range_params(days: int) -> Dict[str, str]:
    """
    일수를 기준으로 시간 범위 파라미터를 계산합니다.
    
    Args:
        days: 최근 일수
        
    Returns:
        시작일과 종료일이 포함된 사전
    """
    today = datetime.now().date()
    start_date = today - timedelta(days=days)
    
    return {
        "start_date": start_date.isoformat(),
        "end_date": today.isoformat()
    }

def clean_url(url: str) -> str:
    """
    URL을 정리합니다.
    
    Args:
        url: 원본 URL
        
    Returns:
        정리된 URL
    """
    if not url:
        return ""
    
    # HTTPS로 변환
    if url.startswith("http:"):
        url = "https:" + url[5:]
    
    # URL에서 추적 파라미터 제거
    tracking_params = ["utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content"]
    if "?" in url:
        base_url, query_string = url.split("?", 1)
        params = query_string.split("&")
        clean_params = [p for p in params if not any(p.startswith(tp + "=") for tp in tracking_params)]
        
        if clean_params:
            url = base_url + "?" + "&".join(clean_params)
        else:
            url = base_url
            
    return url 