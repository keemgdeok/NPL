import streamlit as st
from datetime import datetime, timedelta
import pandas as pd

# --- 추가: 상수 정의 ---
DEFAULT_KEYWORD_LIMIT = 30
DEFAULT_NETWORK_DEPTH = 1
LATEST_NEWS_COUNT = 5
# --------------------

from .api_initializer import get_api_client, clear_api_cache
from .components import (
    render_header,
    render_stats_summary,
    render_sentiment_distribution,
    render_sentiment_trend,
    render_bar_chart, 
    render_keyword_network,
    render_keyword_cloud,
    render_article_card,
    render_error_message
)
from .utils import (
    format_datetime,
    init_session_state,
    get_time_range_params
)

# 스트림릿 페이지 설정
st.set_page_config(
    page_title="뉴스 분석 대시보드",
    page_icon="📰",
    layout="wide",
    initial_sidebar_state="expanded"
)

def main():
    """
    메인 대시보드 페이지를 렌더링합니다.
    """
    # 세션 상태 초기화
    init_session_state(
        dashboard_days=7,
        dashboard_selected_category=None
    )
    
    # 헤더 렌더링
    render_header()
    
    # API 클라이언트 초기화
    api_client = get_api_client()
    
    # 사이드바 설정
    with st.sidebar:
        st.subheader("데이터 필터")
    
        # 날짜 범위 슬라이더
        days = st.slider(
            "기간 (일)",
        min_value=1,
        max_value=30,
            value=st.session_state.dashboard_days,
            step=1,
            key="dashboard_days_slider",
            help="분석할 뉴스 기사의 기간을 선택하세요."
    )
        st.session_state.dashboard_days = days
    
    # 카테고리 선택
        try:
            categories = api_client.get_categories()
            all_option = [{"id": None, "name": "전체 카테고리"}]
            category_options = all_option + categories
            
            selected_category = st.selectbox(
        "카테고리",
                options=[c["id"] for c in category_options],
                format_func=lambda x: next((c["name"] for c in category_options if c["id"] == x), "전체 카테고리"),
                index=0,
                key="dashboard_category_select",
                help="분석할 특정 카테고리를 선택하세요."
            )
            st.session_state.dashboard_selected_category = selected_category
        except Exception as e:
            st.error(f"카테고리를 불러오는데 실패했습니다: {str(e)}")
            categories = []
        
        # 데이터 새로고침 버튼
        if st.button("데이터 새로고침", key="refresh_data"):
            clear_api_cache()
    
    # API 요청 파라미터
    params = get_time_range_params(st.session_state.dashboard_days)
    params["category"] = st.session_state.dashboard_selected_category
    
    # 통계 요약
    try:
        stats = api_client.get_stats_summary(**params)
        render_stats_summary(stats)
    except Exception as e:
        render_error_message(
            f"통계 요약 데이터를 불러오는데 실패했습니다: {str(e)}",
            "네트워크 연결을 확인하거나 나중에 다시 시도해주세요."
        )
        stats = {}  # 오류 발생 시 빈 딕셔너리로 초기화
    
    # 데이터 분석 섹션
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("감성 분포")
        try:
            if stats:
                sentiment_data = {
                    "positive": stats.get("positive_percent", 0) / 100,
                    "neutral": stats.get("neutral_percent", 0) / 100,
                    "negative": stats.get("negative_percent", 0) / 100
                }
                
                render_sentiment_distribution(sentiment_data)
            else:
                st.info("감성 분포 데이터가 없습니다.")
        except Exception as e:
            render_error_message(
                f"감성 분포 데이터를 불러오는데 실패했습니다: {str(e)}",
                "네트워크 연결을 확인하거나 나중에 다시 시도해주세요."
            )
    
    with col2:
        st.subheader("카테고리 분포")
        try:
            if stats and "categories" in stats and stats["categories"]:
                categories_data = sorted(
                    stats["categories"], 
                    key=lambda x: x.get("count", 0),
                    reverse=True
                )[:10]
                
                render_bar_chart(
                    categories_data,
                    x_field="name",
                    y_field="count",
                    color="#1976D2",
                    x_label="카테고리",
                    y_label="기사 수",
                    height=350
                )
            else:
                st.info("카테고리 분포 데이터가 없습니다.")
        except Exception as e:
            render_error_message(
                f"카테고리 분포 데이터를 불러오는데 실패했습니다: {str(e)}",
                "네트워크 연결을 확인하거나 나중에 다시 시도해주세요."
            )
    
    # 감성 트렌드
    st.subheader("감성 트렌드")
    try:
        timeline_params = params.copy()
        timeline_params["interval"] = "day"
        
        sentiment_trend_data = api_client.get_sentiment_trends(**timeline_params)
        
        if sentiment_trend_data and "data" in sentiment_trend_data and sentiment_trend_data["data"]:
            render_sentiment_trend(sentiment_trend_data, interval=timeline_params["interval"])
        else:
            st.info("감성 트렌드 데이터가 없습니다.")
    except Exception as e:
        render_error_message(
            f"감성 트렌드 데이터를 불러오는데 실패했습니다: {str(e)}",
            "네트워크 연결을 확인하거나 나중에 다시 시도해주세요."
        )
    
    # 키워드 및 토픽 분석
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("인기 키워드")
        try:
            keyword_params = params.copy()
            keyword_params["limit"] = DEFAULT_KEYWORD_LIMIT
            
            trending_keywords_data = api_client.get_trending_keywords(**keyword_params)
            
            if trending_keywords_data and "keywords" in trending_keywords_data and trending_keywords_data["keywords"]:
                top_keywords = trending_keywords_data["keywords"]
                render_keyword_cloud(top_keywords, title=None)
            else:
                st.info("키워드 데이터가 없습니다.")
                top_keywords = []
        except Exception as e:
            render_error_message(
                f"키워드 데이터를 불러오는데 실패했습니다: {str(e)}",
                "네트워크 연결을 확인하거나 나중에 다시 시도해주세요."
            )
            top_keywords = []
    
    with col2:
        st.subheader("키워드 관계")
        try:
            if top_keywords:
                root_keyword = top_keywords[0].get("keyword")
                if root_keyword:
                    network_params = params.copy()
                    network_params["keyword"] = root_keyword
                    network_params["depth"] = DEFAULT_NETWORK_DEPTH
                    
                    network_data = api_client.get_keyword_network(**network_params)
                    
                    if network_data and "nodes" in network_data and network_data["nodes"]:
                        render_keyword_network(network_data, height=300)
                    else:
                        st.info(f"'{root_keyword}' 관련 키워드 네트워크 데이터가 없습니다.")
                else:
                    st.info("키워드 관계를 표시할 기준 키워드가 없습니다.")
            else:
                st.info("키워드 관계를 표시할 키워드 데이터가 없습니다.")
        except Exception as e:
            render_error_message(
                f"키워드 네트워크 데이터를 불러오는데 실패했습니다: {str(e)}",
                "네트워크 연결을 확인하거나 나중에 다시 시도해주세요."
            )
    
    # 최신 뉴스 기사
    st.subheader("최신 뉴스 기사")
    try:
        search_params = params.copy()
        search_params.update({
            "page": 1,
            "items_per_page": LATEST_NEWS_COUNT,
            "sort": "published_at",
            "sort_direction": "desc"
        })
        
        search_results = api_client.search_articles(**search_params)
        
        if search_results and "articles" in search_results and search_results["articles"]:
            for article in search_results["articles"]:
                sentiment_info = article.get("sentiment_analysis", {}).get("overall_sentiment", {})
                sentiment_label = sentiment_info.get("sentiment", "neutral")
                
                render_article_card(
                    title=article.get("title", "제목 없음"),
                    url=article.get("url", "#"),
                    category=article.get("category", "카테고리 없음"),
                    published_at=format_datetime(article.get("published_at")),
                    sentiment=sentiment_label,
                    content=article.get("content", "")[:200] + "..." if article.get("content") else None,
                    keywords=article.get("keywords", []),
                    topics=article.get("topic_analysis", {}).get("main_topics", [])
                )
        else:
            st.info("최신 뉴스 기사가 없습니다.")
    except Exception as e:
        render_error_message(
            f"최신 뉴스 기사를 불러오는데 실패했습니다: {str(e)}",
            "네트워크 연결을 확인하거나 나중에 다시 시도해주세요."
        )

if __name__ == "__main__":
    main() 