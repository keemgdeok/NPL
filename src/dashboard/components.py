import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
from typing import Dict, Any, List
import pandas as pd

def render_header():
    """헤더 렌더링"""
    st.title("네이버 뉴스 분석 대시보드")
    st.markdown("""
    이 대시보드는 네이버 뉴스의 토픽 모델링 및 감정 분석 결과를 시각화합니다.
    """)

def render_stats_summary(summary: Dict[str, Any]):
    """전체 통계 요약 렌더링"""
    st.header("전체 통계 요약")
    
    # 전체 기사 수
    st.metric("전체 기사 수", summary["total_articles"])
    
    # 카테고리별 기사 수 차트
    category_data = []
    for cat in summary["categories"]:
        category_data.append({
            "category": cat["category"],
            "count": cat["article_count"]
        })
    
    df = pd.DataFrame(category_data)
    fig = px.bar(df, x="category", y="count", title="카테고리별 기사 수")
    st.plotly_chart(fig)

def render_category_summary(summary: Dict[str, Any]):
    """카테고리별 통계 요약 렌더링"""
    st.header(f"{summary['category']} 카테고리 분석")
    
    col1, col2 = st.columns(2)
    
    # 감정 분포 파이 차트
    with col1:
        sentiment_df = pd.DataFrame([
            {"sentiment": k, "count": v}
            for k, v in summary["sentiment_distribution"].items()
        ])
        fig = px.pie(
            sentiment_df,
            values="count",
            names="sentiment",
            title="감정 분포"
        )
        st.plotly_chart(fig)
    
    # 주요 토픽 바 차트
    with col2:
        topic_data = []
        for topic in summary["top_topics"]:
            topic_data.append({
                "topic": f"Topic {topic['topic_id']}",
                "count": topic["count"],
                "keywords": ", ".join(topic["keywords"][:5])
            })
        
        topic_df = pd.DataFrame(topic_data)
        fig = px.bar(
            topic_df,
            x="topic",
            y="count",
            title="주요 토픽",
            hover_data=["keywords"]
        )
        st.plotly_chart(fig)
    
    # 토픽 키워드
    st.subheader("주요 토픽 키워드")
    for topic in summary["top_topics"]:
        st.markdown(f"**Topic {topic['topic_id']}**: {', '.join(topic['keywords'][:10])}")

def render_article_list(articles: List[Dict[str, Any]]):
    """기사 목록 렌더링"""
    st.header("최근 기사")
    
    for article in articles:
        with st.expander(article["title"]):
            st.markdown(f"**언론사**: {article['press']}")
            st.markdown(f"**카테고리**: {article['category']}")
            st.markdown(f"**작성일**: {article['published_at']}")
            
            # 감정 분석 결과
            if article.get("sentiment_analysis"):
                sentiment = article["sentiment_analysis"]["overall_sentiment"]
                st.markdown(f"**감정 분석**: {sentiment['sentiment']}")
                
                # 감정 점수 차트
                scores = sentiment["scores"]
                score_df = pd.DataFrame([
                    {"sentiment": k, "score": v}
                    for k, v in scores.items()
                ])
                fig = px.bar(
                    score_df,
                    x="sentiment",
                    y="score",
                    title="감정 점수"
                )
                st.plotly_chart(fig)
            
            # 토픽 분석 결과
            if article.get("topic_analysis"):
                st.markdown("**주요 토픽 키워드**")
                for idx, keywords in enumerate(article["topic_analysis"]["topic_keywords"]):
                    if idx in article["topic_analysis"]["main_topics"]:
                        st.markdown(f"- Topic {idx}: {', '.join(keywords[:5])}")
            
            st.markdown("**본문 미리보기**")
            st.markdown(article["content"][:300] + "...") 