import streamlit as st
from datetime import datetime, timedelta
import pandas as pd

from ..api_initializer import get_api_client
from ..components import (
    render_sentiment_distribution, 
    render_sentiment_trend, 
    render_article_card,
    render_error_message
)
from ..utils import (
    format_datetime,
    init_session_state,
    paginate_dataframe,
    create_pagination_ui
)

def sentiment_page():
    """감성 분석 페이지를 렌더링합니다."""
    # 페이지 제목 설정
    st.title("📊 뉴스 감성 분석")
    st.markdown("뉴스 기사의 감성 분석 결과와 트렌드를 확인할 수 있습니다.")
    
    # 세션 상태 초기화
    init_session_state(
        sentiment_page_current=1,
        sentiment_page_items_per_page=5,
        sentiment_selected_category=None,
        sentiment_days=7,
        sentiment_interval="day"
    )
    
    # API 클라이언트 초기화
    api_client = get_api_client()
    
    # 사이드바 필터 설정
    with st.sidebar:
        st.subheader("필터 설정")
        
        # 날짜 범위 슬라이더
        days = st.slider(
            "분석 기간 (일)",
            min_value=1,
            max_value=30, 
            value=st.session_state.sentiment_days,
            step=1,
            key="sentiment_days_slider",
            help="분석할 뉴스 기사의 기간을 선택하세요."
        )
        st.session_state.sentiment_days = days
        
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
                key="sentiment_category_select",
                help="분석할 특정 카테고리를 선택하세요."
            )
            st.session_state.sentiment_selected_category = selected_category
        except Exception as e:
            st.error(f"카테고리를 불러오는데 실패했습니다: {str(e)}")
            categories = []
            st.session_state.sentiment_selected_category = None
        
        # 시간 간격 선택
        interval_options = {
            "hour": "시간별",
            "day": "일별",
            "week": "주별"
        }
        
        selected_interval = st.radio(
            "시간 간격",
            options=list(interval_options.keys()),
            format_func=lambda x: interval_options.get(x, x),
            index=list(interval_options.keys()).index(st.session_state.sentiment_interval),
            key="sentiment_interval_radio",
            help="감성 트렌드 분석의 시간 간격을 선택하세요."
        )
        st.session_state.sentiment_interval = selected_interval
    
    # API 요청 파라미터
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days)
    
    params = {
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "category": st.session_state.sentiment_selected_category
    }
    
    # 감성 분포 표시
    st.subheader("감성 분포")
    
    try:
        stats = api_client.get_stats_summary(**params)
        
        if stats:
            sentiment_data = {
                "positive": stats.get("positive_percent", 0) / 100,
                "neutral": stats.get("neutral_percent", 0) / 100,
                "negative": stats.get("negative_percent", 0) / 100
            }
            
            render_sentiment_distribution(sentiment_data, "전체 기사 감성 분포")
        else:
            st.info("감성 분포 데이터가 없습니다.")
    except Exception as e:
        render_error_message(
            f"감성 분포 데이터를 불러오는데 실패했습니다: {str(e)}",
            "네트워크 연결을 확인하거나 나중에 다시 시도해주세요."
        )
    
    # 감성 트렌드 분석
    st.subheader("감성 트렌드 분석")
    
    try:
        timeline_params = {
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "interval": st.session_state.sentiment_interval,
            "category": st.session_state.sentiment_selected_category
        }
        
        timeline_data = api_client.get_article_timeline(**timeline_params)
        
        if timeline_data:
            render_sentiment_trend(
                timeline_data, 
                interval=st.session_state.sentiment_interval,
                title=f"기간별 감성 트렌드 분석 ({interval_options[st.session_state.sentiment_interval]})"
            )
        else:
            st.info("감성 트렌드 데이터가 없습니다.")
    except Exception as e:
        render_error_message(
            f"감성 트렌드 데이터를 불러오는데 실패했습니다: {str(e)}",
            "네트워크 연결을 확인하거나 나중에 다시 시도해주세요."
        )
    
    # 카테고리별 감성 분포 (선택한 카테고리가 없을 때만 표시)
    if not st.session_state.sentiment_selected_category:
        st.subheader("카테고리별 감성 분포")
        
        try:
            category_data = api_client.get_category_summary(
                start_date=start_date.isoformat(),
                end_date=end_date.isoformat()
            )
            
            if category_data and len(category_data) > 0:
                # 데이터 프레임 생성
                df = pd.DataFrame(category_data)
                
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
                    hide_index=True
                )
            else:
                st.info("카테고리별 감성 데이터가 없습니다.")
        except Exception as e:
            render_error_message(
                f"카테고리별 감성 데이터를 불러오는데 실패했습니다: {str(e)}",
                "네트워크 연결을 확인하거나 나중에 다시 시도해주세요."
            )
    
    # 최근 감성별 뉴스 기사 표시
    st.subheader("최근 기사 감성 분석")
    
    sentiment_tabs = st.tabs(["긍정적 기사", "중립적 기사", "부정적 기사"])
    
    for i, sentiment in enumerate(["positive", "neutral", "negative"]):
        with sentiment_tabs[i]:
            try:
                # 감성별 기사 검색
                search_params = {
                    "start_date": start_date.isoformat(),
                    "end_date": end_date.isoformat(),
                    "category": st.session_state.sentiment_selected_category,
                    "sentiment": sentiment,
                    "page": st.session_state.sentiment_page_current,
                    "items_per_page": st.session_state.sentiment_page_items_per_page
                }
                
                search_results = api_client.search_articles(**search_params)
                
                if search_results and "articles" in search_results and len(search_results["articles"]) > 0:
                    articles = search_results["articles"]
                    total_items = search_results.get("total", len(articles))
                    
                    # 페이지네이션 처리
                    paginated_df = paginate_dataframe(
                        pd.DataFrame(articles),
                        page=st.session_state.sentiment_page_current,
                        items_per_page=st.session_state.sentiment_page_items_per_page
                    )
                    
                    # 기사 렌더링
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
                    create_pagination_ui(
                        total_items=total_items,
                        page=st.session_state.sentiment_page_current,
                        items_per_page=st.session_state.sentiment_page_items_per_page,
                        key_prefix="sentiment"
                    )
                else:
                    st.info(f"해당 조건에 맞는 기사가 없습니다.")
            except Exception as e:
                render_error_message(
                    f"기사를 불러오는데 실패했습니다: {str(e)}",
                    "네트워크 연결을 확인하거나 나중에 다시 시도해주세요."
                ) 