import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
import os
from typing import List, Dict, Any, Optional

from ..api_client import APIClient
from ..utils import init_session_state
from ..components import render_bar_chart, render_keyword_network

# API 클라이언트 초기화
@st.cache_resource
def get_api_client():
    """API 클라이언트 객체를 생성하고 캐싱합니다."""
    return APIClient()

@st.cache_data(ttl=300)
def render_wordcloud(data: List[Dict[str, Any]]) -> None:
    """워드클라우드 시각화 함수
    
    Args:
        data: 키워드 데이터 목록
    """
    if not data:
        st.info("키워드 데이터가 없습니다.")
        return
    
    # 데이터 변환
    keywords = {item["keyword"]: item["score"] for item in data}
    
    # 임의의 좌표 생성 (시각적 표현을 위해)
    n_words = len(keywords)
    np.random.seed(42)  # 일관성을 위한 시드 설정
    
    # 원형 레이아웃을 위한 좌표 계산
    angles = np.linspace(0, 2*np.pi, n_words, endpoint=False)
    x = np.cos(angles)
    y = np.sin(angles)
    
    # 키워드 크기 계산 (정규화)
    scores = np.array(list(keywords.values()))
    sizes = 15 + 85 * (scores - min(scores)) / (max(scores) - min(scores) + 1e-10)
    
    # 키워드와 점수 목록
    keywords_list = list(keywords.keys())
    
    # 워드클라우드 시각화
    fig = go.Figure()
    
    # 점 추가 (배경)
    fig.add_trace(go.Scatter(
        x=x, y=y,
        mode='markers',
        marker=dict(
            size=sizes,
            color=np.random.randint(50, 200, n_words),
            colorscale='Viridis',
            opacity=0.8,
            line=dict(width=1, color='white')
        ),
        text=keywords_list,
        hoverinfo='text+marker.size',
        hovertemplate='<b>%{text}</b><br>점수: %{marker.size:.1f}<extra></extra>'
    ))
    
    # 텍스트 추가
    fig.add_trace(go.Scatter(
        x=x, y=y,
        mode='text',
        text=keywords_list,
        textfont=dict(
            size=np.sqrt(sizes) * 2,
            color='white'
        ),
        hoverinfo='none'
    ))
    
    # 레이아웃 설정
    fig.update_layout(
        title="키워드 워드클라우드",
        height=600,
        showlegend=False,
        xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
        yaxis=dict(showgrid=False, zeroline=False, showticklabels=False)
    )
    
    # 종횡비 유지
    fig.update_yaxes(
        scaleanchor="x",
        scaleratio=1,
    )
    
    st.plotly_chart(fig, use_container_width=True)

def keywords_page():
    """키워드 분석 페이지"""
    # 페이지 설정
    st.title("🔑 키워드 분석")
    st.markdown("트렌딩 키워드와 키워드 간 관계를 시각화합니다.")
    
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
    
    # 트렌딩 키워드 가져오기
    try:
        with st.spinner("트렌딩 키워드 데이터를 불러오는 중..."):
            keyword_params = params.copy()
            keyword_params["limit"] = 50  # 더 많은 키워드 가져오기
            keywords_data = client.get_trending_keywords(**keyword_params)
            
            if keywords_data and keywords_data.get("keywords"):
                # 탭 구성
                tab1, tab2, tab3 = st.tabs(["📊 키워드 랭킹", "☁️ 워드클라우드", "🔍 키워드 네트워크"])
                
                # 탭 1: 키워드 랭킹
                with tab1:
                    st.header("인기 키워드 Top 20")
                    
                    render_bar_chart(
                        data=keywords_data["keywords"][:20],
                        x_field="keyword",
                        y_field="score",
                        title="키워드 중요도 점수",
                        color="#3f51b5"
                    )
                    
                    # 키워드 테이블로도 표시
                    st.markdown("### 키워드 테이블")
                    
                    # 표시할 데이터 가공
                    display_df = pd.DataFrame(keywords_data["keywords"][:50])
                    if "sentiment_distribution" in display_df.columns:
                        # 감성 분포에서 주요 감성 추출
                        def get_main_sentiment(dist):
                            if not dist:
                                return "neutral"
                            return max(dist.items(), key=lambda x: x[1])[0]
                        
                        display_df["sentiment"] = display_df["sentiment_distribution"].apply(get_main_sentiment)
                    
                    # 필요한 컬럼만 선택하고 이름 변경
                    cols_to_show = ["keyword", "count", "score", "sentiment"]
                    cols_to_show = [col for col in cols_to_show if col in display_df.columns]
                    
                    if cols_to_show:
                        display_df = display_df[cols_to_show]
                        
                        # 컬럼명 변경
                        column_rename = {
                            "keyword": "키워드",
                            "count": "빈도수",
                            "score": "중요도",
                            "sentiment": "주요 감성"
                        }
                        
                        display_df = display_df.rename(columns={k: v for k, v in column_rename.items() if k in display_df.columns})
                        
                        # 점수를 소수점 2자리로 포맷팅
                        if "중요도" in display_df.columns:
                            display_df["중요도"] = display_df["중요도"].apply(lambda x: f"{x:.2f}")
                        
                        # 감성 레이블 변환
                        sentiment_map = {
                            "positive": "긍정",
                            "neutral": "중립", 
                            "negative": "부정"
                        }
                        
                        if "주요 감성" in display_df.columns:
                            display_df["주요 감성"] = display_df["주요 감성"].map(
                                lambda x: sentiment_map.get(x, x)
                            )
                        
                        st.dataframe(
                            display_df,
                            use_container_width=True,
                            column_config={
                                "빈도수": st.column_config.NumberColumn(format="%d"),
                            }
                        )
                    else:
                        st.info("키워드 테이블을 표시할 데이터가 부족합니다.")
                
                # 탭 2: 워드클라우드
                with tab2:
                    st.header("키워드 워드클라우드")
                    
                    render_wordcloud(keywords_data["keywords"][:40])
                
                # 탭 3: 키워드 네트워크
                with tab3:
                    st.header("키워드 네트워크 분석")
                    
                    # 키워드 선택
                    keyword_options = [k["keyword"] for k in keywords_data["keywords"][:20]]
                    if keyword_options:
                        selected_keyword = st.selectbox(
                            "키워드 선택",
                            options=keyword_options
                        )
                        
                        col1, col2 = st.columns(2)
                        
                        with col1:
                            depth = st.slider("네트워크 깊이", min_value=1, max_value=3, value=1)
                        
                        with col2:
                            st.markdown("깊이가 클수록 연관 키워드의 범위가 넓어집니다.")
                        
                        try:
                            with st.spinner(f"'{selected_keyword}' 키워드 네트워크 데이터를 불러오는 중..."):
                                # 네트워크 데이터 가져오기
                                network_params = {
                                    "keyword": selected_keyword,
                                    "depth": depth,
                                    "days": params["days"]
                                }
                                
                                network_data = client.get_keyword_network(**network_params)
                                
                                if network_data and network_data.get("nodes"):
                                    # 네트워크 시각화
                                    render_keyword_network(network_data)
                                    
                                    # 키워드 정보 표시
                                    st.markdown(f"### '{selected_keyword}' 키워드 분석")
                                    
                                    # 선택한 키워드에 대한 정보
                                    keyword_info = next((k for k in keywords_data["keywords"] if k["keyword"] == selected_keyword), None)
                                    
                                    if keyword_info:
                                        col1, col2, col3 = st.columns(3)
                                        
                                        with col1:
                                            st.metric("중요도 점수", f"{keyword_info.get('score', 0):.2f}")
                                        
                                        with col2:
                                            st.metric("출현 빈도", f"{keyword_info.get('count', 0)}")
                                        
                                        with col3:
                                            sentiment = keyword_info.get('sentiment', 'neutral')
                                            sentiment_text = "긍정" if sentiment == "positive" else "부정" if sentiment == "negative" else "중립"
                                            sentiment_emoji = "😀" if sentiment == "positive" else "😞" if sentiment == "negative" else "😐"
                                            st.metric("주요 감성", f"{sentiment_text} {sentiment_emoji}")
                                    
                                    # 관련 키워드 수 및 관계 정보
                                    st.markdown(f"### 네트워크 정보")
                                    
                                    col1, col2 = st.columns(2)
                                    with col1:
                                        st.metric("관련 키워드 수", len(network_data.get("nodes", [])) - 1)
                                    with col2:
                                        st.metric("연결 관계 수", len(network_data.get("edges", [])))
                                else:
                                    st.info(f"'{selected_keyword}' 키워드에 대한 네트워크 데이터가 없습니다.")
                        except Exception as e:
                            st.error(f"키워드 네트워크 데이터 불러오기 실패: {str(e)}")
                    else:
                        st.info("키워드 선택 옵션이 없습니다.")
            else:
                st.info("트렌딩 키워드 데이터를 불러올 수 없습니다.")
    except Exception as e:
        st.error(f"키워드 데이터 불러오기 실패: {str(e)}")

if __name__ == "__main__":
    keywords_page() 