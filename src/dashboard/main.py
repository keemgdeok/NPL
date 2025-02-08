import streamlit as st
from datetime import datetime, timedelta

from .api_client import APIClient
from .components import (
    render_header,
    render_stats_summary,
    render_category_summary,
    render_article_list
)

# 페이지 설정
st.set_page_config(
    page_title="네이버 뉴스 분석 대시보드",
    page_icon="📰",
    layout="wide"
)

# API 클라이언트 초기화
@st.cache_resource
def get_api_client():
    return APIClient()

def main():
    # 헤더 렌더링
    render_header()
    
    # API 클라이언트 가져오기
    client = get_api_client()
    
    # 사이드바 설정
    st.sidebar.title("설정")
    
    # 기간 선택
    days = st.sidebar.slider(
        "분석 기간 (일)",
        min_value=1,
        max_value=30,
        value=7
    )
    
    # 카테고리 선택
    categories = client.get_categories()
    selected_category = st.sidebar.selectbox(
        "카테고리",
        ["전체"] + categories
    )
    
    # 감정 선택
    selected_sentiment = st.sidebar.selectbox(
        "감정",
        ["전체", "positive", "neutral", "negative"]
    )
    
    try:
        # 전체 통계 요약
        stats_summary = client.get_stats_summary(days=days)
        render_stats_summary(stats_summary)
        
        # 카테고리별 분석
        if selected_category != "전체":
            category_summary = client.get_category_summary(
                category=selected_category,
                days=days
            )
            render_category_summary(category_summary)
        
        # 기사 목록
        articles_response = client.get_articles(
            category=selected_category if selected_category != "전체" else None,
            sentiment=selected_sentiment if selected_sentiment != "전체" else None,
            days=days,
            size=10
        )
        render_article_list(articles_response["articles"])
        
    except Exception as e:
        st.error(f"데이터를 불러오는 중 오류가 발생했습니다: {str(e)}")

if __name__ == "__main__":
    main() 