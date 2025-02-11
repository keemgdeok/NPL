from typing import List, Dict
import json
from kafka.admin import KafkaAdminClient, NewTopic
import logging
from .config import NaverNewsConfig

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class KafkaTopicManager:
    """Kafka 토픽 관리자"""
    
    def __init__(self, bootstrap_servers: str = None):
        self.admin_client = KafkaAdminClient(
            bootstrap_servers=bootstrap_servers or NaverNewsConfig.KAFKA_BOOTSTRAP_SERVERS
        )
        
        # 뉴스 카테고리
        self.CATEGORIES = [
            "economy",      # 경제
            "business",     # 기업/산업
            "society",      # 사회
            "world",        # 국제
            "politics",     # 정치
            "it",          # IT/과학
            "culture"       # 문화
        ]
        
        # 처리 단계
        self.PROCESSING_STAGES = [
            "raw",          # 원본 데이터 (JSON 스크래핑 결과)
            "processed",    # 전처리 완료
            "topic",        # 토픽 분석 완료
            "sentiment"     # 감정 분석 완료
        ]
    
    def get_topic_name(self, category: str, stage: str) -> str:
        """토픽 이름 생성
        
        Args:
            category (str): 뉴스 카테고리
            stage (str): 처리 단계
            
        Returns:
            str: Kafka 토픽 이름 (예: news.economy.raw)
        """
        return f"news.{category}.{stage}"
    
    def create_topics(self, partitions: int = 3, replication_factor: int = 1):
        """모든 토픽 생성
        
        카테고리별로 처리 단계에 따른 토픽 생성
        예: news.economy.raw, news.business.processed 등
        
        Args:
            partitions (int): 파티션 수 (기본값: 3)
            replication_factor (int): 복제 팩터 (기본값: 1)
        """
        topic_list = []
        
        for category in self.CATEGORIES:
            for stage in self.PROCESSING_STAGES:
                topic_name = self.get_topic_name(category, stage)
                topic = NewTopic(
                    name=topic_name,
                    num_partitions=partitions,
                    replication_factor=replication_factor
                )
                topic_list.append(topic)
                logger.info(f"토픽 생성 준비: {topic_name}")
        
        try:
            self.admin_client.create_topics(new_topics=topic_list, validate_only=False)
            logger.info("모든 토픽이 성공적으로 생성되었습니다.")
            
            # 생성된 토픽 목록 출력
            logger.info("\n=== 생성된 토픽 목록 ===")
            for category in self.CATEGORIES:
                logger.info(f"\n[{category}]")
                for stage in self.PROCESSING_STAGES:
                    logger.info(f"  - {self.get_topic_name(category, stage)}")
                        
        except Exception as e:
            logger.error(f"토픽 생성 중 오류 발생: {str(e)}")
    
    def delete_topics(self):
        """모든 토픽 삭제"""
        try:
            existing_topics = self.admin_client.list_topics()
            news_topics = [topic for topic in existing_topics if topic.startswith("news.")]
            
            if news_topics:
                self.admin_client.delete_topics(news_topics)
                logger.info("모든 뉴스 토픽이 삭제되었습니다.")
            else:
                logger.info("삭제할 뉴스 토픽이 없습니다.")
                
        except Exception as e:
            logger.error(f"토픽 삭제 중 오류 발생: {str(e)}")
    
    def close(self):
        """리소스 정리"""
        self.admin_client.close()

def main():
    """메인 실행 함수"""
    manager = KafkaTopicManager()
    
    try:
        # 기존 토픽 삭제 (선택사항)
        # manager.delete_topics()
        
        # 새로운 토픽 생성
        manager.create_topics()
        
    finally:
        manager.close()

if __name__ == "__main__":
    main() 