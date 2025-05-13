import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from typing import Dict, List, Any, Optional, Union, Tuple
from datetime import datetime
import time
import networkx as nx  # 명시적 의존성 선언

from .utils import get_sentiment_emoji, get_sentiment_color, get_sentiment_label

def render_header():
    """
    대시보드 헤더를 렌더링합니다.
    """
    col1, col2 = st.columns([3, 1])
    
    with col1:
        st.title("📰 뉴스 분석 대시보드")
        st.markdown("뉴스 데이터를 분석하여 트렌드와 통찰력을 제공합니다.")
    
    with col2:
        st.image("https://www.naver.com/favicon.ico", width=50)
        st.markdown("**Powered by NAVER News**")

def render_stats_summary(stats: Dict[str, Any]):
    """
    통계 요약 정보를 렌더링합니다.
    
    Args:
        stats: 통계 요약 데이터
    """
    if not stats:
        st.warning("통계 데이터를 불러올 수 없습니다.")
        return
    
    total_articles = stats.get("total_articles", 0)
    
    # 통계 요약 표시
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.metric("총 기사 수", f"{total_articles:,}건")
    
    with col2:
        positive_percent = stats.get("positive_percent", 0)
        neutral_percent = stats.get("neutral_percent", 0)
        negative_percent = stats.get("negative_percent", 0)
        
        max_sentiment = max(
            ("긍정", positive_percent), 
            ("중립", neutral_percent), 
            ("부정", negative_percent),
            key=lambda x: x[1]
        )
        
        st.metric("주요 감성", f"{max_sentiment[0]} ({max_sentiment[1]}%)")
    
    with col3:
        categories = stats.get("categories", [])
        if categories:
            max_category = max(categories, key=lambda x: x.get("count", 0))
            category_name = max_category.get("name", "")
            category_count = max_category.get("count", 0)
            
            if category_name and category_count:
                st.metric("최다 카테고리", f"{category_name} ({category_count:,}건)")
    
    # 기간 표시
    time_range = stats.get("time_range", {})
    start_date = time_range.get("start")
    end_date = time_range.get("end")
    
    if start_date and end_date:
        if isinstance(start_date, str):
            start_date = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
        if isinstance(end_date, str):
            end_date = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
            
        st.caption(f"분석 기간: {start_date.strftime('%Y년 %m월 %d일')} ~ {end_date.strftime('%Y년 %m월 %d일')}")

def render_article_card(
    title: str,
    url: str,
    category: str,
    published_at: str,
    sentiment: str = "neutral",
    content: Optional[str] = None,
    keywords: Optional[List[str]] = None,
    topics: Optional[List[str]] = None,
    show_buttons: bool = False
) -> None:
    """
    뉴스 기사 카드를 렌더링합니다.
    
    Args:
        title: 기사 제목
        url: 기사 URL
        category: 기사 카테고리
        published_at: 기사 발행일자 (포맷팅된 문자열)
        sentiment: 감성 분석 결과 (positive, neutral, negative)
        content: 기사 내용 미리보기
        keywords: 주요 키워드 목록
        topics: 관련 토픽 목록
        show_buttons: 버튼 표시 여부
    """
    # 감성에 따른 색상 및 이모지 설정
    sentiment_emoji = get_sentiment_emoji(sentiment)
    sentiment_color = get_sentiment_color(sentiment)
    sentiment_text = get_sentiment_label(sentiment)
    
    # 카드 컨테이너
    with st.container():
        # 카드 헤더 (제목 및 카테고리)
        col1, col2 = st.columns([4, 1])
        
        with col1:
            st.markdown(f"### [{title}]({url})")
        
        with col2:
            st.markdown(
                f"""
                <div style="display: flex; justify-content: flex-end; align-items: center; gap: 5px;">
                    <span style="background-color: #f0f0f0; color: #333; padding: 5px 10px; border-radius: 15px; font-size: 0.8em;">
                        {category}
                    </span>
                    <span style="background-color: {sentiment_color}; color: white; padding: 5px 10px; border-radius: 15px; font-size: 0.8em;">
                        {sentiment_text} {sentiment_emoji}
                    </span>
                </div>
                """,
                unsafe_allow_html=True
            )
        
        # 기사 내용 및 메타 정보
        if content:
            st.markdown(f"<p style='color: #555;'>{content}</p>", unsafe_allow_html=True)
        
        # 발행일
        st.markdown(f"<small style='color: #888;'>발행일: {published_at}</small>", unsafe_allow_html=True)
        
        # 키워드 및 토픽 표시
        if keywords or topics:
            st.markdown("<div style='margin-top: 10px;'>", unsafe_allow_html=True)
            
            if keywords:
                st.markdown(
                    f"""
                    <div style="display: flex; flex-wrap: wrap; gap: 5px; margin-bottom: 5px;">
                        <span style="color: #888; font-size: 0.8em;">키워드:</span>
                        {' '.join([f'<span style="background-color: #e0f7fa; color: #006064; padding: 2px 8px; border-radius: 12px; font-size: 0.8em;">{k}</span>' for k in keywords[:5]])}
                    </div>
                    """,
                    unsafe_allow_html=True
                )
            
            if topics:
                st.markdown(
                    f"""
                    <div style="display: flex; flex-wrap: wrap; gap: 5px;">
                        <span style="color: #888; font-size: 0.8em;">토픽:</span>
                        {' '.join([f'<span style="background-color: #edf4fb; color: #1565c0; padding: 2px 8px; border-radius: 12px; font-size: 0.8em;">{t}</span>' for t in topics[:3]])}
                    </div>
                    """,
                    unsafe_allow_html=True
                )
            
            st.markdown("</div>", unsafe_allow_html=True)
        
        # 버튼 영역
        if show_buttons:
            col1, col2, col3 = st.columns([1, 1, 2])
            
            with col1:
                st.markdown(f"[원문 보기]({url})")
            
            with col2:
                if st.button("요약 보기", key=f"summary_{hash(url)}"):
                    with st.spinner("요약을 불러오는 중..."):
                        # 여기서는 임시로 지연만 추가
                        # 실제로는 API 호출을 통해 요약 데이터를 가져와야 함
                        time.sleep(0.5)
                        st.info("아직 요약 기능이 구현되지 않았습니다.")

def render_sentiment_distribution(
    data: Dict[str, float],
    title: str = "감성 분포",
    height: int = 350
) -> None:
    """
    감성 분포 파이 차트를 렌더링합니다.
    
    Args:
        data: 감성별 비율 데이터 (예: {"positive": 0.3, "neutral": 0.5, "negative": 0.2})
        title: 차트 제목
        height: 차트 높이
    """
    if not data:
        st.info("감성 분포 데이터가 없습니다.")
        return
    
    # 데이터 가공
    df = pd.DataFrame({
        "감성": [get_sentiment_label(k) for k in data.keys()],
        "비율": list(data.values()),
        "색상": [get_sentiment_color(k) for k in data.keys()],
        "이모지": [get_sentiment_emoji(k) for k in data.keys()]
    })
    
    # 파이 차트
    fig = px.pie(
        df,
        names="감성",
        values="비율",
        color="감성",
        color_discrete_sequence=df["색상"].tolist(),
        hole=0.4,
        custom_data=["이모지"]
    )
    
    # 레이블 및 호버 정보 설정
    fig.update_traces(
        textinfo="percent+label",
        hovertemplate="<b>%{label} %{customdata[0]}</b><br>비율: %{percent}<extra></extra>"
    )
    
    # 레이아웃 설정
    fig.update_layout(
        title=title,
        height=height,
        showlegend=True,
        legend=dict(orientation="h", yanchor="bottom", y=-0.2)
    )
    
    st.plotly_chart(fig, use_container_width=True)

def render_sentiment_trend(
    data: Dict[str, Dict[str, float]],
    interval: str = "day",
    title: str = "감성 트렌드",
    height: int = 400
) -> None:
    """
    감성 트렌드 선 그래프를 렌더링합니다.
    
    Args:
        data: 시간별 감성 분포 데이터
              예: {"2023-01-01T00:00:00": {"positive": 0.3, "neutral": 0.5, "negative": 0.2}, ...}
        interval: 시간 간격 (hour, day, week)
        title: 차트 제목
        height: 차트 높이
    """
    if not data:
        st.info("감성 트렌드 데이터가 없습니다.")
        return
    
    # 시간 간격에 따른 포맷 설정
    time_formats = {
        "hour": "%Y-%m-%d %H시",
        "day": "%Y-%m-%d",
        "week": "%Y년 %W주"
    }
    time_format = time_formats.get(interval, "%Y-%m-%d")
    
    # 데이터 가공
    sentiment_types = ["positive", "neutral", "negative"]
    colors = [get_sentiment_color(s) for s in sentiment_types]
    labels = [get_sentiment_label(s) for s in sentiment_types]
    
    # 각 시간별 데이터 추출
    timestamps = []
    sentiments = {s: [] for s in sentiment_types}
    
    for time_str, values in data.items():
        try:
            dt = datetime.fromisoformat(time_str.replace("Z", "+00:00"))
            formatted_time = dt.strftime(time_format)
            timestamps.append(formatted_time)
            
            for s in sentiment_types:
                sentiments[s].append(values.get(s, 0))
        except (ValueError, TypeError):
            continue
    
    if not timestamps:
        st.info("감성 트렌드 데이터를 처리할 수 없습니다.")
        return
    
    # 그래프 생성
    fig = go.Figure()
    
    for i, s in enumerate(sentiment_types):
        fig.add_trace(go.Scatter(
            x=timestamps,
            y=sentiments[s],
            mode="lines",
            name=labels[i],
            line=dict(color=colors[i], width=2),
            stackgroup="one"
        ))
    
    # 레이아웃 설정
    fig.update_layout(
        title=title,
        height=height,
        xaxis=dict(title="날짜"),
        yaxis=dict(title="비율"),
        hovermode="x unified",
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="center",
            x=0.5
        )
    )
    
    st.plotly_chart(fig, use_container_width=True)

def render_bar_chart(
    data: List[Dict[str, Any]],
    x_field: str,
    y_field: str,
    color: str = "#1565C0",
    title: Optional[str] = None,
    x_label: Optional[str] = None,
    y_label: Optional[str] = None,
    orientation: str = "v",
    height: int = 400,
    max_items: int = 20
) -> None:
    """
    바 차트를 렌더링합니다.
    
    Args:
        data: 차트 데이터
        x_field: X축 필드명
        y_field: Y축 필드명
        color: 바 색상
        title: 차트 제목
        x_label: X축 레이블
        y_label: Y축 레이블
        orientation: 차트 방향 ("v"=세로, "h"=가로)
        height: 차트 높이
        max_items: 최대 표시 항목 수
    """
    if not data:
        st.info("바 차트 데이터가 없습니다.")
        return
    
    # 데이터 크기 제한
    data = data[:max_items]
    
    # 데이터프레임 변환
    df = pd.DataFrame(data)
    
    # 필수 필드 확인
    if x_field not in df.columns or y_field not in df.columns:
        st.warning(f"필드가 존재하지 않습니다: {x_field} 또는 {y_field}")
        return
    
    # 가로 바 차트일 경우 x와 y 필드 교체
    if orientation == "h":
        x_field, y_field = y_field, x_field
    
    # 차트 생성
    fig = px.bar(
        df,
        x=x_field,
        y=y_field,
        orientation=orientation,
        title=title,
        labels={
            x_field: x_label or x_field,
            y_field: y_label or y_field
        },
        color_discrete_sequence=[color]
    )
    
    # 레이아웃 설정
    fig.update_layout(
        height=height,
        margin=dict(l=0, r=0, t=40, b=0)
    )
    
    # 축 설정
    if orientation == "v":
        fig.update_yaxes(title=y_label or y_field)
        fig.update_xaxes(title=x_label or x_field)
    else:
        fig.update_yaxes(title=x_label or x_field)
        fig.update_xaxes(title=y_label or y_field)
    
    st.plotly_chart(fig, use_container_width=True)

def render_keyword_network(
    network_data: Dict[str, List[Dict[str, Any]]],
    title: str = "키워드 네트워크",
    height: int = 600
) -> None:
    """
    키워드 네트워크 그래프를 렌더링합니다.
    이 함수는 NetworkX 라이브러리에 의존합니다.
    
    Args:
        network_data: 네트워크 데이터 (노드 및 엣지 정보)
        title: 차트 제목
        height: 차트 높이
    """
    if (not network_data or 
        "nodes" not in network_data or 
        "edges" not in network_data or 
        not network_data["nodes"]):
        st.info("키워드 네트워크 데이터가 없습니다.")
        return
    
    # 그래프 생성
    G = nx.Graph()
    
    # 노드 추가
    for node in network_data["nodes"]:
        node_id = node.get("id")
        label = node.get("label", node_id)
        weight = node.get("weight", 1)
        category = node.get("category", "default")
        
        if node_id:
            G.add_node(
                node_id,
                label=label,
                weight=weight,
                category=category
            )
    
    # 엣지 추가
    for edge in network_data.get("edges", []):
        source = edge.get("source")
        target = edge.get("target")
        weight = edge.get("weight", 1)
        
        if source and target and source in G.nodes and target in G.nodes:
            G.add_edge(source, target, weight=weight)
    
    if not G.nodes:
        st.info("네트워크 그래프를 생성할 수 없습니다.")
        return
    
    # 레이아웃 계산
    try:
        if len(G.nodes) < 100:
            pos = nx.spring_layout(G, seed=42, k=0.2)
        else:
            pos = nx.kamada_kawai_layout(G)
    except Exception:
        pos = {node: (np.random.rand(), np.random.rand()) for node in G.nodes}
    
    # 노드 크기 및 색상 설정
    node_size = [G.nodes[node].get("weight", 1) * 20 for node in G.nodes]
    node_color = ["#1976D2" if G.nodes[node].get("category") == "root" else "#90CAF9" for node in G.nodes]
    
    # 엣지 너비 설정
    edge_width = [G.edges[edge].get("weight", 1) / 2 for edge in G.edges]
    
    # 플로틀리 그래프 생성
    edge_trace_list = []
    for edge in G.edges:
        x0, y0 = pos[edge[0]]
        x1, y1 = pos[edge[1]]
        weight = G.edges[edge].get("weight", 1)
        
        edge_trace = go.Scatter(
            x=[x0, x1, None],
            y=[y0, y1, None],
            mode="lines",
            line=dict(width=weight / 2, color="#CFCFCF"),
            hoverinfo="none"
        )
        edge_trace_list.append(edge_trace)
    
    node_trace = go.Scatter(
        x=[pos[node][0] for node in G.nodes],
        y=[pos[node][1] for node in G.nodes],
        mode="markers",
        marker=dict(
            size=node_size,
            color=node_color,
            line=dict(width=2, color="#FFFFFF")
        ),
        text=[G.nodes[node].get("label", node) for node in G.nodes],
        hoverinfo="text"
    )
    
    # 레이아웃 설정
    layout = go.Layout(
        title=title,
        showlegend=False,
        hovermode="closest",
        margin=dict(b=0, l=0, r=0, t=40),
        xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
        yaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
        height=height
    )
    
    # 그래프 생성 및 표시
    fig = go.Figure(data=edge_trace_list + [node_trace], layout=layout)
    st.plotly_chart(fig, use_container_width=True)

def render_keyword_cloud(
    keywords: List[Dict[str, Any]],
    keyword_field: str = "keyword",
    weight_field: str = "score",
    count_field: str = "count",
    on_click_handler: Optional[str] = None,
    title: Optional[str] = None
) -> None:
    """
    키워드 태그 클라우드를 렌더링합니다.
    
    Args:
        keywords: 키워드 데이터 목록
        keyword_field: 키워드 필드명
        weight_field: 가중치 필드명 (폰트 크기 결정)
        count_field: 개수 필드명
        on_click_handler: 클릭 시 실행할 JavaScript 핸들러
        title: 클라우드 제목
    """
    if not keywords:
        st.info("키워드 데이터가 없습니다.")
        return
    
    if title:
        st.subheader(title)
    
    # 키워드 태그 클라우드 스타일 정의
    st.markdown("""
    <style>
    .keyword-cloud {
        display: flex;
        flex-wrap: wrap;
        gap: 8px;
        margin-top: 0.5rem;
        margin-bottom: 1rem;
    }
    .keyword-tag {
        padding: 8px 16px;
        border-radius: 20px;
        background-color: #e6f3ff;
        color: #1e88e5;
        font-weight: 500;
        text-align: center;
        transition: all 0.2s;
        cursor: pointer;
    }
    .keyword-tag:hover {
        background-color: #1e88e5;
        color: white;
    }
    </style>
    <div class="keyword-cloud">
    """, unsafe_allow_html=True)
    
    # 폰트 크기 범위 설정
    font_sizes = {
        "min": 12,
        "max": 24
    }
    
    # 가중치 최소/최대값 계산
    weights = [k.get(weight_field, 0) for k in keywords]
    weight_min = min(weights) if weights else 0
    weight_max = max(weights) if weights else 1
    weight_range = max(weight_max - weight_min, 1)  # 0으로 나누기 방지
    
    # 키워드 태그 렌더링
    for keyword in keywords:
        keyword_text = keyword.get(keyword_field, "")
        keyword_count = keyword.get(count_field, 0)
        keyword_weight = keyword.get(weight_field, 0)
        
        if keyword_text:
            # 폰트 크기 정규화
            normalized_weight = (keyword_weight - weight_min) / weight_range
            font_size = font_sizes["min"] + normalized_weight * (font_sizes["max"] - font_sizes["min"])
            
            # 클릭 이벤트 핸들러 추가
            if on_click_handler:
                onclick = f"onclick=\"{on_click_handler.replace('{keyword}', keyword_text)}\""
            else:
                onclick = ""
            
            # 태그 렌더링
            st.markdown(
                f"""
                <a 
                    href="javascript:void(0)" 
                    class="keyword-tag" 
                    style="font-size: {font_size}px;"
                    {onclick}
                >
                    {keyword_text} ({keyword_count})
                </a>
                """,
                unsafe_allow_html=True
            )
    
    st.markdown("</div>", unsafe_allow_html=True)

def render_loading_animation() -> None:
    """
    로딩 애니메이션을 렌더링합니다.
    """
    st.markdown("""
    <style>
    .loading-container {
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        height: 200px;
    }
    .loading-spinner {
        width: 50px;
        height: 50px;
        border: 4px solid rgba(0, 0, 0, 0.1);
        border-radius: 50%;
        border-top: 4px solid #2196F3;
        animation: spin 1s linear infinite;
    }
    @keyframes spin {
        0% { transform: rotate(0deg); }
        100% { transform: rotate(360deg); }
    }
    .loading-text {
        margin-top: 20px;
        font-size: 16px;
        color: #555;
    }
    </style>
    <div class="loading-container">
        <div class="loading-spinner"></div>
        <div class="loading-text">데이터를 불러오는 중입니다...</div>
    </div>
    """, unsafe_allow_html=True)

def render_error_message(message: str, suggestion: Optional[str] = None) -> None:
    """
    오류 메시지를 렌더링합니다.
    
    Args:
        message: 오류 메시지
        suggestion: 해결 방법 제안
    """
    st.markdown(f"""
    <div style="padding: 15px; background-color: #FFEBEE; border-left: 6px solid #F44336; margin-bottom: 15px;">
        <h3 style="color: #D32F2F; margin-top: 0; margin-bottom: 10px;">오류가 발생했습니다</h3>
        <p style="margin: 0; color: #555;">{message}</p>
        {f'<p style="margin-top: 10px; color: #555; font-style: italic;">{suggestion}</p>' if suggestion else ''}
    </div>
    """, unsafe_allow_html=True)

def render_timeline_chart(
    data: List[Dict[str, Any]],
    date_field: str = "date",
    value_field: str = "count",
    title: str = "시간별 추이",
    height: int = 400
) -> None:
    """
    시간별 추이 차트를 렌더링합니다.
    
    Args:
        data: 시간별 데이터 목록
        date_field: 날짜 필드명
        value_field: 값 필드명
        title: 차트 제목
        height: 차트 높이
    """
    if not data:
        st.info("타임라인 데이터가 없습니다.")
        return
    
    # 데이터 가공
    chart_data = []
    
    for point in data:
        date_str = point.get(date_field)
        value = point.get(value_field, 0)
        
        if date_str:
            try:
                date = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
                date_formatted = date.strftime("%Y-%m-%d")
                
                chart_data.append({
                    "날짜": date_formatted,
                    "값": value
                })
            except (ValueError, TypeError):
                pass
    
    if not chart_data:
        st.info("처리 가능한 타임라인 데이터가 없습니다.")
        return
    
    # 데이터프레임 변환
    df = pd.DataFrame(chart_data)
    
    # 차트 생성
    fig = px.line(
        df,
        x="날짜",
        y="값",
        title=title,
        markers=True
    )
    
    # 레이아웃 설정
    fig.update_layout(
        height=height,
        xaxis_title="날짜",
        yaxis_title="값",
        hovermode="x unified"
    )
    
    st.plotly_chart(fig, use_container_width=True) 