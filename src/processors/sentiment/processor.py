from typing import Dict, Any, List
from datetime import datetime, timedelta
import json
from kafka import KafkaConsumer, KafkaProducer
import os
import logging  
import time
from .analyzer import SentimentAnalyzer
from ...collectors.utils.config import Config
# from ...common.database.repositories.article_repository import SentimentArticleRepository # 삭제
# from ...common.database.exceptions import OperationError # 삭제

logger = logging.getLogger("sentiment-processor")

class SentimentProcessor:
    def __init__(self, model_path: str = None):
        # KR-FinBert-SC 금융 도메인 특화 감성분석 모델 사용
        self.analyzer = SentimentAnalyzer(model_path=model_path)
        
        # Repository 초기화 # 삭제
        # self.repository = SentimentArticleRepository() # 삭제
        
        # Kafka 설정 - 모든 카테고리의 processed 토픽 구독
        processed_topics = [f"{Config.KAFKA_TOPIC_PREFIX}.{category}.processed" 
                            for category in Config.CATEGORIES.keys()]
        
        logger.info(f"구독할 토픽 목록: {processed_topics}")
        
        self.consumer = KafkaConsumer(
            *processed_topics,
            bootstrap_servers=Config.KAFKA_BOOTSTRAP_SERVERS,
            value_deserializer=lambda x: json.loads(x.decode('utf-8')),
            auto_offset_reset='latest',
            enable_auto_commit=True,
            group_id="sentiment-processor-group"
        )
        
        self.producer = KafkaProducer(
            bootstrap_servers=Config.KAFKA_BOOTSTRAP_SERVERS,
            value_serializer=lambda x: json.dumps(x).encode('utf-8'),
            # 타임아웃 설정 추가
            request_timeout_ms=30000,         # 30초
            max_block_ms=30000,               # 30초
            api_version_auto_timeout_ms=30000, # 30초
            # 재시도 설정
            retries=5,
            retry_backoff_ms=1000             # 1초 간격으로 재시도
        )
    
    def analyze_article(self, article_data: Dict[str, Any]) -> Dict[str, Any]:
        """기사의 감성 분석
        
        Args:
            article_data: 처리된 뉴스 기사 데이터
            
        Returns:
            Dict: 감성 분석 결과가 추가된 기사 데이터
        """
        try:
            # 원본 내용으로 감성 분석
            original_content = article_data["content"]
            
            # 전체 내용에 대한 감성 분석
            overall_sentiment = self.analyzer.analyze(original_content)
            
            # 감성 분석 결과 추가 (구조 변경)
            article_data["sentiment_analysis"] = overall_sentiment
            
            # 감성 분석 시간 추가
            article_data["sentiment_processed_at"] = datetime.now().isoformat()
            
            return article_data
            
        except Exception as e:
            logger.error(f"감성 분석 오류: {str(e)}")
            # 에러 발생 시 최소한의 감성 분석 결과 추가 (구조 및 기본값 변경)
            article_data["sentiment_analysis"] = {
                "sentiment": "neutral",
                "scores": {"negative": 0.0, "neutral": 1.0, "positive": 0.0}, # KR-FinBert-SC 출력 형식에 맞춘 기본값
                "error": str(e)
            }
            article_data["sentiment_processed_at"] = datetime.now().isoformat()
            return article_data
    
    def process_stream(self):
        """Kafka 스트림 처리"""
        try:
            logger.info("메시지 처리 대기 중...")
            for message in self.consumer:
                try:
                    # 메시지 카테고리 추출
                    topic_parts = message.topic.split('.')
                    category = topic_parts[1] if len(topic_parts) > 1 else "unknown"
                    
                    # 메시지에서 처리된 기사 데이터 파싱
                    article_data = message.value
                    logger.info(f"메시지 수신: {article_data.get('title', 'Unknown Title')} (토픽: {message.topic})")
                    
                    # 기사 감성 분석
                    analyzed_data = self.analyze_article(article_data)
                    logger.info(f"감성 분석 완료: {analyzed_data['title']} (감성: {analyzed_data['sentiment_analysis']['sentiment']})")
                    
                    # 처리된 데이터를 다음 단계로 전송
                    self._send_to_kafka(analyzed_data, category)
                    logger.info(f"Kafka 전송 완료: {analyzed_data['title']} -> {category}.sentiment")
                    
                except Exception as e:
                    logger.error(f"메시지 처리 중 오류 발생: {str(e)}")
                    continue
                    
        except KeyboardInterrupt:
            logger.info("사용자에 의해 처리가 중단되었습니다.")
        finally:
            self.close()
    
    def _send_to_kafka(self, data: Dict[str, Any], category: str):
        """처리된 데이터를 Kafka로 전송
        
        Args:
            data: 전송할 데이터
            category: 뉴스 카테고리
        """
        try:
            # 카테고리별 감정 분석 토픽으로 전송
            topic = f"{Config.KAFKA_TOPIC_PREFIX}.{category}.sentiment"
            self.producer.send(topic, value=data)
            logger.debug(f"Kafka 토픽 전송 완료: {topic}")
        except Exception as e:
            logger.error(f"Kafka 전송 오류: {str(e)}")
    
    def close(self):
        """리소스 정리"""
        self.consumer.close()
        self.producer.close()
        logger.info("모든 리소스가 정리되었습니다.") 