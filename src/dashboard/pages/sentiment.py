import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
import os

from ..api_client import APIClient
from ..utils import init_session_state
from ..components import render_sentiment_chart, render_bar_chart, render_news_card

# API 클라이언트 초기화
@st.cache_resource
def get_api_client():
    """API 클라이언트 객체를 생성하고 캐싱합니다."""
    return APIClient()

def sentiment_page():
    """감성 분석 페이지"""
    # 페이지 설정
    st.title("😀😐😞 감성 분석")
    st.markdown("시간별 감성 변화 추이와 카테고리별 감성 분포를 확인할 수 있습니다.")
    
    # 세션 상태 초기화
    init_session_state()
    
    # API 클라이언트 가져오기
    client = get_api_client()
    
    # 사이드바 설정
    st.sidebar.title("설정")
    
    # 날짜 필터 설정
    date_range = st.sidebar.slider(
        "분석 기간 (일)",
        min_value=1,
        max_value=90,
        value=30
    )
    
    # 카테고리 선택
    categories = client.get_categories()
    selected_category = st.sidebar.selectbox(
        "카테고리",
        ["전체"] + categories,
        index=0
    )
    
    category = None if selected_category == "전체" else selected_category
    
    # 기본 API 파라미터
    params = {
        "days": date_range,
        "category": category
    }
    
    # 상단에 감성 요약 차트
    st.header("감성 분포")
    
    try:
        with st.spinner('감성 분포 데이터를 불러오는 중...'):
            stats = client.get_stats_summary(days=date_range)
            
            if stats:
                # 감성 분포 차트 (도넛 차트)
                sentiment_data = [
                    {"sentiment": "긍정", "percent": stats["positive_percent"]},
                    {"sentiment": "중립", "percent": stats["neutral_percent"]},
                    {"sentiment": "부정", "percent": stats["negative_percent"]}
                ]
                
                df = pd.DataFrame(sentiment_data)
                
                fig = go.Figure(data=[go.Pie(
                    labels=df["sentiment"],
                    values=df["percent"],
                    hole=.4,
                    marker=dict(
                        colors=["rgba(76, 175, 80, 0.8)", "rgba(158, 158, 158, 0.8)", "rgba(244, 67, 54, 0.8)"]
                    )
                )])
                
                fig.update_layout(
                    title="감성 분포",
                    height=400,
                    annotations=[dict(text=f"{stats['total_articles']:,}건", x=0.5, y=0.5, font_size=20, showarrow=False)]
                )
                
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("감성 분포 데이터를 불러올 수 없습니다.")
    except Exception as e:
        st.error(f"감성 분포 데이터 불러오기 실패: {str(e)}")
    
    # 감성 트렌드 차트
    st.header("감성 트렌드")
    
    # 시간 간격 선택
    interval = st.radio(
        "시간 간격",
        options=["시간별", "일별", "주별"],
        horizontal=True,
        index=1
    )
    
    interval_map = {
        "시간별": "hour",
        "일별": "day",
        "주별": "week"
    }
    
    try:
        with st.spinner(f"{interval} 감성 트렌드 데이터를 불러오는 중..."):
            sentiment_params = params.copy()
            sentiment_params["interval"] = interval_map[interval]
            sentiment_data = client.get_sentiment_trends(**sentiment_params)
            
            if sentiment_data and sentiment_data.get("points"):
                render_sentiment_chart(
                    data=sentiment_data["points"],
                    title=f"{interval} 감성 분석 추이"
                )
            else:
                st.info("해당 기간에 감성 데이터가 없습니다.")
    except Exception as e:
        st.error(f"감성 트렌드 데이터 불러오기 실패: {str(e)}")
    
    # 카테고리별 감성 분포
    if not category:  # 특정 카테고리가 선택되지 않았을 때만 표시
        st.header("카테고리별 감성 분포")
        
        try:
            with st.spinner("카테고리별 감성 분포 데이터를 불러오는 중..."):
                # 각 카테고리별 감성 요약 가져오기
                category_data = []
                
                for cat in categories:
                    cat_stats = client.get_category_summary(cat, days=date_range)
                    
                    if cat_stats:
                        sentiment_dist = cat_stats.get("sentiment_distribution", {})
                        total = sum(sentiment_dist.values())
                        
                        if total > 0:
                            category_data.append({
                                "category": cat,
                                "positive": sentiment_dist.get("positive", 0) / total * 100,
                                "neutral": sentiment_dist.get("neutral", 0) / total * 100,
                                "negative": sentiment_dist.get("negative", 0) / total * 100,
                                "total": cat_stats.get("article_count", 0)
                            })
                
                if category_data:
                    df = pd.DataFrame(category_data)
                    
                    # 긍정 비율로 정렬
                    df = df.sort_values("positive", ascending=False)
                    
                    # 막대 차트 (카테고리별 감성 분포)
                    fig = go.Figure()
                    
                    for sentiment, color, name in [
                        ("positive", "rgba(76, 175, 80, 0.8)", "긍정"),
                        ("neutral", "rgba(158, 158, 158, 0.8)", "중립"),
                        ("negative", "rgba(244, 67, 54, 0.8)", "부정")
                    ]:
                        fig.add_trace(go.Bar(
                            name=name,
                            x=df["category"],
                            y=df[sentiment],
                            marker_color=color
                        ))
                    
                    fig.update_layout(
                        barmode="stack",
                        title="카테고리별 감성 분포",
                        height=500,
                        margin=dict(l=20, r=20, t=40, b=80),
                        legend=dict(
                            orientation="h",
                            yanchor="bottom",
                            y=1.02,
                            xanchor="right",
                            x=1
                        ),
                    )
                    
                    # X축 레이블 회전
                    fig.update_xaxes(tickangle=45)
                    
                    st.plotly_chart(fig, use_container_width=True)
                    
                    # 표 형태로도 표시
                    st.markdown("### 카테고리별 감성 통계")
                    
                    # 표시할 데이터 가공
                    display_df = df.copy()
                    display_df = display_df.rename(columns={
                        "category": "카테고리",
                        "positive": "긍정 (%)",
                        "neutral": "중립 (%)",
                        "negative": "부정 (%)",
                        "total": "총 기사 수"
                    })
                    
                    # 소수점 1자리로 표시
                    for col in ["긍정 (%)", "중립 (%)", "부정 (%)"]:
                        display_df[col] = display_df[col].apply(lambda x: f"{x:.1f}")
                    
                    st.dataframe(
                        display_df,
                        use_container_width=True,
                        column_config={
                            "총 기사 수": st.column_config.NumberColumn(format="%d"),
                        }
                    )
                else:
                    st.info("카테고리별 감성 분포 데이터가 없습니다.")
        except Exception as e:
            st.error(f"카테고리별 감성 분포 데이터 불러오기 실패: {str(e)}")
    
    # 감성별 최신 기사
    st.header("감성별 주요 기사")
    
    tab1, tab2, tab3 = st.tabs(["😀 긍정", "😐 중립", "😞 부정"])
    
    for tab, sentiment in [(tab1, "positive"), (tab2, "neutral"), (tab3, "negative")]:
        with tab:
            try:
                with st.spinner(f"{sentiment} 감성 기사를 불러오는 중..."):
                    # 각 감성별 기사 가져오기
                    article_params = {
                        "category": params.get("category"),
                        "sentiment": sentiment,
                        "days": params.get("days"),
                        "page": 1,
                        "size": 5
                    }
                    
                    articles_data = client.get_articles(**article_params)
                    
                    if articles_data and articles_data.get("articles"):
                        for article in articles_data["articles"]:
                            render_news_card(article)
                    else:
                        st.info(f"해당 기간에 {sentiment} 감성의 기사가 없습니다.")
            except Exception as e:
                st.error(f"{sentiment} 감성 기사 불러오기 실패: {str(e)}")

if __name__ == "__main__":
    sentiment_page() 