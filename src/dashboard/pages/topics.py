import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
import yaml
import os
from typing import Dict, List, Any, Optional

from ..api_client import APIClient
from ..utils import init_session_state, format_datetime, format_text
from ..components import render_article_card

# API 클라이언트 초기화
@st.cache_resource
def get_api_client():
    """API 클라이언트 객체를 생성하고 캐싱합니다."""
    return APIClient()

# 토픽 설정 로드
@st.cache_data
def load_topic_config():
    """토픽 설정 파일을 로드합니다."""
    config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config", "topics.yml")
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)
        return config
    except Exception as e:
        st.error(f"토픽 설정 파일을 로드하는 중 오류 발생: {str(e)}")
        return {"topics": {}}

# 토픽별 아이콘 및 색상 설정
@st.cache_data
def get_topic_metadata():
    """토픽별 메타데이터(아이콘, 색상)를 반환합니다."""
    # 기본 토픽 메타데이터
    topic_meta = {
        "정치": {"icon": "🏛️", "color": "#E63946"},
        "경제": {"icon": "💰", "color": "#4CAF50"},
        "사회": {"icon": "👥", "color": "#3F51B5"},
        "문화": {"icon": "🎭", "color": "#9C27B0"},
        "IT/과학": {"icon": "🔬", "color": "#2196F3"},
        "스포츠": {"icon": "⚽", "color": "#FF9800"},
        "세계": {"icon": "🌎", "color": "#607D8B"}
    }
    
    # 설정 파일에서 추가 토픽 메타데이터 로드
    config = load_topic_config()
    for topic_name, topic_info in config.get("topics", {}).items():
        # 기존에 없는 토픽이거나 메타데이터가 있는 경우에만 업데이트
        if topic_name not in topic_meta or topic_info.get("metadata"):
            icon = topic_info.get("metadata", {}).get("icon", "📊")
            color = topic_info.get("metadata", {}).get("color", "#777777")
            topic_meta[topic_name] = {"icon": icon, "color": color}
    
    return topic_meta

def topics_page():
    """토픽 분석 페이지"""
    # 페이지 설정
    st.title("📊 토픽 분석")
    st.markdown("뉴스 기사들을 토픽별로 분류하고 분석합니다.")
    
    # 세션 상태 초기화
    init_session_state()
    
    # API 클라이언트 가져오기
    client = get_api_client()
    
    # 토픽 메타데이터 로드
    topic_meta = get_topic_metadata()
    
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
    
    # 토픽 분포 가져오기
    try:
        with st.spinner("토픽 분석 데이터를 불러오는 중..."):
            topic_distribution = client.get_topic_distribution(**params)
            
            if topic_distribution and topic_distribution.get("topics"):
                # 토픽 분포 데이터 준비
                topic_data = []
                for topic, count in topic_distribution["topics"].items():
                    meta = topic_meta.get(topic, {"icon": "📊", "color": "#777777"})
                    topic_data.append({
                        "토픽": f"{meta['icon']} {topic}",
                        "기사 수": count,
                        "color": meta["color"],
                        "topic_name": topic  # 원래 토픽 이름 저장
                    })
                
                # 토픽 데이터가 있는 경우에만 진행
                if topic_data:
                    topic_df = pd.DataFrame(topic_data)
                    
                    # 토픽별 기사 비율 계산
                    col1, col2 = st.columns([2, 1], gap="large")
                    
                    with col1:
                        st.header("토픽별 기사 분포")
                        
                        # 파이 차트
                        fig = px.pie(
                            topic_df,
                            names="토픽",
                            values="기사 수",
                            color="토픽",
                            color_discrete_sequence=topic_df["color"].tolist(),
                            hole=0.4,
                        )
                        
                        fig.update_layout(
                            height=500,
                            showlegend=True,
                            legend=dict(orientation="h", yanchor="bottom", y=-0.2),
                        )
                        
                        st.plotly_chart(fig, use_container_width=True)
                    
                    with col2:
                        st.header("토픽별 기사 수")
                        
                        # 토픽별 기사 수 표시
                        for idx, row in topic_df.iterrows():
                            st.metric(
                                label=row["토픽"],
                                value=f"{row['기사 수']:,}건",
                            )
                    
                    # 토픽 트렌드 탭과 토픽별 기사 탭 구성
                    tab1, tab2 = st.tabs(["📈 토픽 트렌드", "📰 토픽별 기사"])
                    
                    # 탭 1: 토픽 트렌드
                    with tab1:
                        st.header("토픽 트렌드 분석")
                        
                        try:
                            # 시간 간격 선택
                            interval_options = {"시간별": "hour", "일별": "day", "주별": "week"}
                            selected_interval = st.selectbox(
                                "시간 간격",
                                options=list(interval_options.keys()),
                                index=1
                            )
                            
                            interval = interval_options[selected_interval]
                            
                            # 토픽 트렌드 데이터 가져오기
                            trend_params = params.copy()
                            trend_params["interval"] = interval
                            
                            trend_data = client.get_topic_trends(**trend_params)
                            
                            if trend_data and trend_data.get("trends"):
                                # 트렌드 데이터 가공
                                trend_rows = []
                                for timestamp, topics in trend_data["trends"].items():
                                    dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                                    for topic, count in topics.items():
                                        trend_rows.append({
                                            "timestamp": dt,
                                            "topic": topic,
                                            "count": count,
                                            "display_topic": f"{topic_meta.get(topic, {}).get('icon', '📊')} {topic}"
                                        })
                                
                                if trend_rows:
                                    trend_df = pd.DataFrame(trend_rows)
                                    
                                    # 시계열 차트
                                    fig = px.line(
                                        trend_df,
                                        x="timestamp", 
                                        y="count",
                                        color="display_topic",
                                        labels={
                                            "timestamp": "시간",
                                            "count": "기사 수",
                                            "display_topic": "토픽"
                                        },
                                        color_discrete_map={
                                            f"{topic_meta.get(t, {}).get('icon', '📊')} {t}": topic_meta.get(t, {}).get('color', '#777777') 
                                            for t in trend_df["topic"].unique()
                                        }
                                    )
                                    
                                    fig.update_layout(
                                        height=600,
                                        xaxis_title="시간",
                                        yaxis_title="기사 수",
                                        legend_title="토픽",
                                        hovermode="x unified"
                                    )
                                    
                                    # X축 형식 설정
                                    if interval == "hour":
                                        date_format = "%Y-%m-%d %H시"
                                    elif interval == "day":
                                        date_format = "%Y-%m-%d"
                                    else:  # week
                                        date_format = "%Y-%m-%d"
                                    
                                    # 호버 템플릿 설정
                                    fig.update_traces(
                                        hovertemplate="<b>%{fullData.name}</b><br>"
                                                      "시간: %{x|" + date_format + "}<br>"
                                                      "기사 수: %{y}건<extra></extra>"
                                    )
                                    
                                    st.plotly_chart(fig, use_container_width=True)
                                else:
                                    st.info("트렌드 데이터가 충분하지 않습니다.")
                            else:
                                st.info("트렌드 데이터를 불러올 수 없습니다.")
                        except Exception as e:
                            st.error(f"토픽 트렌드 데이터 불러오기 실패: {str(e)}")
                    
                    # 탭 2: 토픽별 기사
                    with tab2:
                        st.header("토픽별 최신 기사")
                        
                        # 토픽 선택
                        topic_options = [row["topic_name"] for idx, row in topic_df.iterrows()]
                        selected_topic = st.selectbox(
                            "토픽 선택",
                            options=topic_options,
                            format_func=lambda x: f"{topic_meta.get(x, {}).get('icon', '📊')} {x}"
                        )
                        
                        try:
                            # 선택한 토픽의 최근 기사 가져오기
                            article_params = {
                                "topic": selected_topic,
                                "limit": 10,
                                "category": params.get("category")
                            }
                            
                            topic_articles = client.get_articles_by_topic(**article_params)
                            
                            if topic_articles and topic_articles.get("articles"):
                                st.subheader(f"{topic_meta.get(selected_topic, {}).get('icon', '📊')} {selected_topic} 관련 최신 기사")
                                
                                for article in topic_articles["articles"]:
                                    # 기사 카드 렌더링
                                    render_article_card(
                                        title=article.get("title", "제목 없음"),
                                        url=article.get("url", "#"),
                                        category=article.get("category", "일반"),
                                        published_at=format_datetime(article.get("published_at")),
                                        sentiment=article.get("sentiment", "neutral"),
                                        content=format_text(article.get("content", "내용 없음"), max_length=150)
                                    )
                                    
                                    # 구분선 추가
                                    st.markdown("---")
                            else:
                                st.info(f"{selected_topic} 토픽의 기사가 없습니다.")
                        except Exception as e:
                            st.error(f"토픽 기사 데이터 불러오기 실패: {str(e)}")
                    
                    # 토픽 키워드 시각화
                    st.header("토픽별 주요 키워드")
                    
                    try:
                        # 모든 토픽에 대한 키워드 데이터 가져오기
                        keywords_data = client.get_topic_keywords(**params)
                        
                        if keywords_data and keywords_data.get("topics"):
                            # 토픽별 키워드 차트
                            topic_cols = st.columns(min(3, len(keywords_data["topics"])))
                            
                            for i, (topic, keywords) in enumerate(keywords_data["topics"].items()):
                                with topic_cols[i % 3]:
                                    meta = topic_meta.get(topic, {"icon": "📊", "color": "#777777"})
                                    
                                    st.subheader(f"{meta['icon']} {topic}")
                                    
                                    if keywords:
                                        # 키워드 데이터 가공
                                        keyword_df = pd.DataFrame([
                                            {"keyword": k, "score": s} 
                                            for k, s in keywords.items()
                                        ]).sort_values("score", ascending=False).head(10)
                                        
                                        # 수평 막대 차트
                                        fig = px.bar(
                                            keyword_df,
                                            y="keyword",
                                            x="score",
                                            orientation="h",
                                            color_discrete_sequence=[meta["color"]],
                                            labels={"keyword": "키워드", "score": "점수"}
                                        )
                                        
                                        fig.update_layout(
                                            height=350,
                                            margin=dict(l=10, r=10, t=10, b=10),
                                            xaxis_title="",
                                            yaxis_title=""
                                        )
                                        
                                        st.plotly_chart(fig, use_container_width=True)
                                    else:
                                        st.info("키워드 데이터가 없습니다.")
                        else:
                            st.info("토픽별 키워드 데이터를 불러올 수 없습니다.")
                    except Exception as e:
                        st.error(f"토픽 키워드 데이터 불러오기 실패: {str(e)}")
                else:
                    st.info("표시할 토픽 데이터가 없습니다.")
            else:
                st.info("토픽 분포 데이터를 불러올 수 없습니다.")
    except Exception as e:
        st.error(f"토픽 분석 데이터 불러오기 실패: {str(e)}")

if __name__ == "__main__":
    topics_page() 