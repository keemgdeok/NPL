import streamlit as st
import pandas as pd
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta

from ..api_initializer import get_api_client
from ..utils import (
    init_session_state, 
    format_datetime, 
    create_pagination_ui,
    paginate_dataframe
)
from ..components import (
    render_article_card, 
    render_error_message, 
    render_keyword_cloud
)

def search_page():
    """
    검색 페이지 렌더링
    """
    st.title("🔍 뉴스 검색")
    st.markdown("키워드로 뉴스 기사를 검색하고 결과를 필터링합니다.")
    
    # 세션 상태 초기화
    init_session_state(
        search_query="",
        search_page_current=1,
        search_items_per_page=10,
        search_selected_category=None,
        search_days=30,
        search_sort_by="relevance",
        search_sort_direction="desc"
    )
    
    # API 클라이언트 초기화
    api_client = get_api_client()
    
    try:
        # 카테고리 가져오기
        categories = api_client.get_categories()
        all_option = [{"id": None, "name": "전체 카테고리"}]
        category_options = all_option + categories
    except Exception as e:
        categories = []
        category_options = all_option
        render_error_message(
            f"카테고리 정보를 불러오는데 실패했습니다: {str(e)}",
            "네트워크 연결을 확인하거나 나중에 다시 시도해주세요."
        )
    
    # 사이드바 - 검색 필터
    with st.sidebar:
        st.subheader("검색 필터")
        
        # 카테고리 선택
        selected_category = st.selectbox(
            "카테고리",
            options=[c["id"] for c in category_options],
            format_func=lambda x: next((c["name"] for c in category_options if c["id"] == x), "전체 카테고리"),
            index=0,
            key="search_category_select"
        )
        st.session_state.search_selected_category = selected_category
        
        # 날짜 필터 설정
        days = st.slider(
            "분석 기간 (일)",
            min_value=1,
            max_value=90,
            value=st.session_state.search_days,
            key="search_days_slider"
        )
        st.session_state.search_days = days
        
        # 정렬 옵션
        sort_options = {
            "관련성": "relevance",
            "최신순": "published_at",
            "긍정 감성순": "sentiment.positive",
            "부정 감성순": "sentiment.negative"
        }
        
        sort_by = st.selectbox(
            "정렬 기준",
            options=list(sort_options.keys()),
            index=0,
            key="search_sort_by_select"
        )
        st.session_state.search_sort_by = sort_options[sort_by]
        
        sort_direction = st.selectbox(
            "정렬 방향",
            options=["내림차순", "오름차순"],
            index=0,
            key="search_sort_direction_select"
        )
        st.session_state.search_sort_direction = "desc" if sort_direction == "내림차순" else "asc"
    
    # 검색 폼
    with st.form(key="search_form"):
        # 검색창
        query = st.text_input(
            "키워드 검색",
            value=st.session_state.search_query,
            placeholder="검색어를 입력하세요...",
            key="search_query_input"
        )
        
        # 검색 버튼
        search_submitted = st.form_submit_button(label="검색")
        
        if search_submitted:
            # 세션 상태에 검색어 저장
            st.session_state.search_query = query
            # 검색할 때 첫 페이지로 초기화
            st.session_state.search_page_current = 1
    
    # 검색 결과 표시
    if st.session_state.search_query:
        try:
            with st.spinner("검색 중..."):
                # 검색 파라미터 설정
                end_date = datetime.now()
                start_date = end_date - timedelta(days=st.session_state.search_days)
                
                search_params = {
                    "query": st.session_state.search_query,
                    "category": st.session_state.search_selected_category,
                    "start_date": start_date.isoformat(),
                    "end_date": end_date.isoformat(),
                    "page": st.session_state.search_page_current,
                    "items_per_page": st.session_state.search_items_per_page,
                    "sort": st.session_state.search_sort_by,
                    "sort_direction": st.session_state.search_sort_direction
                }
                
                # API 호출
                search_results = api_client.search_articles(**search_params)
                
                if search_results and "articles" in search_results and search_results["articles"]:
                    articles = search_results["articles"]
                    total_results = search_results.get("total", 0)
                    
                    # 검색 결과 요약
                    st.subheader(f"검색 결과: {total_results}개의 기사")
                    
                    # 데이터프레임으로 변환
                    df = pd.DataFrame(articles)
                    
                    # 페이지네이션 처리
                    paginated_df = paginate_dataframe(
                        df,
                        page=st.session_state.search_page_current,
                        items_per_page=st.session_state.search_items_per_page
                    )
                    
                    # 검색 결과 목록
                    for _, article in paginated_df.iterrows():
                        render_article_card(
                            title=article.get("title", "제목 없음"),
                            url=article.get("url", "#"),
                            category=article.get("category", "카테고리 없음"),
                            published_at=format_datetime(article.get("published_at")),
                            sentiment=article.get("sentiment", "neutral"),
                            content=article.get("content", "")[:150] + "..." if article.get("content") else None,
                            keywords=article.get("keywords", []),
                            topics=article.get("topics", [])
                        )
                    
                    # 페이지네이션 UI 생성
                    new_page = create_pagination_ui(
                        total_items=total_results,
                        page=st.session_state.search_page_current,
                        items_per_page=st.session_state.search_items_per_page,
                        key_prefix="search_page"
                    )
                    
                    # 페이지 변경 시 세션 상태 업데이트
                    if new_page != st.session_state.search_page_current:
                        st.session_state.search_page_current = new_page
                        st.rerun()
                else:
                    st.info(f"'{st.session_state.search_query}'에 대한 검색 결과가 없습니다.")
        except Exception as e:
            render_error_message(
                f"검색 결과를 불러오는데 실패했습니다: {str(e)}",
                "네트워크 연결을 확인하거나 나중에 다시 시도해주세요."
            )
    else:
        # 검색어가 없는 경우 트렌딩 키워드 표시
        st.subheader("인기 검색어")
        
        try:
            end_date = datetime.now()
            start_date = end_date - timedelta(days=st.session_state.search_days)
            
            trending_params = {
                "category": st.session_state.search_selected_category,
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "limit": 20
            }
            
            trending_keywords = api_client.get_trending_keywords(**trending_params)
            
            if trending_keywords and trending_keywords.get("keywords"):
                # 키워드 클라우드 컴포넌트 사용
                render_keyword_cloud(
                    trending_keywords["keywords"],
                    keyword_field="keyword",
                    weight_field="score",
                    count_field="count",
                    on_click_handler="document.querySelector('input[aria-label=\"키워드 검색\"]').value = '{keyword}'; document.querySelector('button[type=\"submit\"]').click();"
                )
            else:
                st.info("인기 검색어 정보를 불러올 수 없습니다.")
        except Exception as e:
            render_error_message(
                f"인기 검색어를 불러오는데 실패했습니다: {str(e)}",
                "네트워크 연결을 확인하거나 나중에 다시 시도해주세요."
            )
        
        # 카테고리별 요약 정보
        st.subheader("카테고리별 요약")
        
        try:
            # 카테고리별 요약 정보 가져오기
            end_date = datetime.now()
            start_date = end_date - timedelta(days=st.session_state.search_days)
            
            category_summary = api_client.get_category_summary(
                start_date=start_date.isoformat(),
                end_date=end_date.isoformat()
            )
            
            if category_summary and len(category_summary) > 0:
                # 데이터프레임 준비
                df = pd.DataFrame(category_summary)
                
                # 컬럼명 한글화
                df.columns = [
                    "카테고리", "기사 수", "긍정 비율", "중립 비율", "부정 비율"
                ]
                
                # 비율 컬럼 형식 변경
                for col in ["긍정 비율", "중립 비율", "부정 비율"]:
                    df[col] = df[col].apply(lambda x: f"{x:.1f}%")
                
                # 데이터프레임 표시
                st.dataframe(
                    df,
                    column_config={
                        "카테고리": st.column_config.TextColumn("카테고리"),
                        "기사 수": st.column_config.NumberColumn("기사 수", format="%d건"),
                        "긍정 비율": st.column_config.ProgressColumn(
                            "긍정 비율", 
                            format="%s",
                            min_value=0,
                            max_value=100,
                            color="#4CAF50"
                        ),
                        "중립 비율": st.column_config.ProgressColumn(
                            "중립 비율", 
                            format="%s",
                            min_value=0,
                            max_value=100,
                            color="#2196F3"
                        ),
                        "부정 비율": st.column_config.ProgressColumn(
                            "부정 비율", 
                            format="%s",
                            min_value=0,
                            max_value=100,
                            color="#F44336"
                        )
                    },
                    hide_index=True,
                    use_container_width=True
                )
            else:
                st.info("카테고리별 요약 정보가 없습니다.")
        except Exception as e:
            render_error_message(
                f"카테고리별 요약 정보를 불러오는데 실패했습니다: {str(e)}",
                "네트워크 연결을 확인하거나 나중에 다시 시도해주세요."
            )

if __name__ == "__main__":
    search_page() 