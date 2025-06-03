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
    def __init__(self, model_path: str = None, idle_timeout: int = 0):
        self.idle_timeout = idle_timeout
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
            group_id="sentiment-processor-group",
            # idle_timeout을 사용하기 위해 consumer_timeout_ms는 poll()에서 관리
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
        # idle_timeout을 밀리초 단위로 변환, 0 이하면 무한 대기로 간주 (None 전달)
        poll_timeout_ms = self.idle_timeout * 1000 if self.idle_timeout and self.idle_timeout > 0 else None
        
        try:
            logger.info(f"메시지 처리 대기 중... (유휴 시간 제한: {self.idle_timeout}초)")
            
            while True: # 명시적인 종료 조건(타임아웃)을 위해 루프 사용
                # poll 메서드를 사용하여 메시지를 가져오고 타임아웃 적용
                # poll_timeout_ms가 None이면 무한 대기
                message_pack = self.consumer.poll(timeout_ms=poll_timeout_ms, max_records=1) 
                
                if not message_pack: # 타임아웃 발생 (메시지 없음)
                    if poll_timeout_ms is not None: # 타임아웃이 설정된 경우에만
                        logger.info(f"{self.idle_timeout}초 동안 메시지가 없어 처리를 종료합니다.")
                        break # 루프를 빠져나가 finally 블록에서 정리
                    else: # 타임아웃이 설정되지 않은 경우 (무한 대기) 계속 대기
                        continue

                for tp, messages in message_pack.items():
                    for message in messages:
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
                            
                            # 수동 커밋 (enable_auto_commit=False 일 경우)
                            # self.consumer.commit() 
                            
                        except Exception as e:
                            logger.error(f"메시지 처리 중 오류 발생: {str(e)}", exc_info=True) # 상세 오류 로깅
                            # 특정 메시지 처리 실패 시 해당 메시지 건너뛰고 계속 진행
                            continue
                            
        except KeyboardInterrupt:
            logger.info("사용자에 의해 처리가 중단되었습니다.")
        # 다른 예외들은 run_processor.py의 메인 try-except 블록에서 처리됨
        finally:
            logger.info("스트림 처리 루프 종료. 리소스 정리 시도...")
            self.close() # 여기서 항상 close()가 호출되도록 보장
    
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