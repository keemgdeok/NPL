from typing import Dict, Any, List
import json
from kafka import KafkaConsumer
import logging
import asyncio
from concurrent.futures import ThreadPoolExecutor
import time
from botocore.exceptions import ClientError
import aioboto3

from .utils.config import Config

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class S3StorageManager:
    """Kafka raw 토픽의 뉴스 데이터를 S3에 저장하는 관리자
    
    - 데이터를 시간별로 파티셔닝하여 저장
    - 배치 처리를 통한 성능 최적화
    - 멀티스레딩을 통한 병렬 업로드
    """
    
    def __init__(self, max_retries=None, retry_delay=None):
        # 설정 검증
        Config.validate()
        
        # 재시도 설정
        self.max_retries = max_retries or int(Config.MAX_RETRIES)
        self.retry_delay = retry_delay or int(Config.RETRY_DELAY)
        
        # Kafka Consumer 설정
        self.consumer = KafkaConsumer(
            bootstrap_servers=Config.KAFKA_BOOTSTRAP_SERVERS,
            group_id='s3-storage-manager',
            value_deserializer=lambda x: json.loads(x.decode('utf-8')),
            auto_offset_reset='earliest',
            enable_auto_commit=False
        )
        
        # S3 설정 (aioboto3 세션 생성)
        self.session = aioboto3.Session()
        self.bucket_name = Config.S3_BUCKET_NAME
        
        # S3 연결 테스트
        asyncio.create_task(self._test_s3_connection())
        
        # 배치 처리를 위한 버퍼
        self.batch_size = Config.STORAGE_BATCH_SIZE
        self.flush_interval = Config.STORAGE_FLUSH_INTERVAL
        self.message_buffer: Dict[str, List[Dict]] = {}
        self.last_flush_time = time.time()
        
        # 스레드 풀 설정
        self.executor = ThreadPoolExecutor(max_workers=Config.STORAGE_MAX_WORKERS)
        
        # raw 토픽 구독
        self._subscribe_to_raw_topics()
    
    async def _test_s3_connection(self):
        """S3 연결 테스트"""
        try:
            async with self.session.client('s3',
                aws_access_key_id=Config.AWS_ACCESS_KEY_ID,
                aws_secret_access_key=Config.AWS_SECRET_ACCESS_KEY,
                region_name=Config.AWS_REGION
            ) as s3:
                await s3.head_bucket(Bucket=self.bucket_name)
                logger.info(f"S3 버킷 '{self.bucket_name}' 연결 성공")
        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == '404':
                logger.error(f"버킷 '{self.bucket_name}'이 존재하지 않습니다.")
            elif error_code == '403':
                logger.error("S3 버킷에 접근할 권한이 없습니다.")
            else:
                logger.error(f"S3 연결 오류: {str(e)}")
            raise
    
    def _subscribe_to_raw_topics(self):
        """raw 단계의 모든 토픽 구독"""
        self.consumer.subscribe(pattern="news\\..*\\.raw")
        logger.info("구독 패턴: news.*.raw")
    
    def _get_s3_key(self, category: str, message_id: str) -> str:
        """S3 키 생성
        
        Args:
            category (str): 뉴스 카테고리
            message_id (str): 메시지 고유 ID
            
        Returns:
            str: S3 키 (예: raw/economy/economy_1234567890_123.json)
        """
        # timestamp = int(time.time())
        return f"raw/{category}/{category}_{message_id}.json"
    
    async def _upload_to_s3(self, key: str, data: List[Dict]):
        """S3에 데이터 업로드"""
        try:
            # JSON 변환
            json_data = json.dumps(data, ensure_ascii=False, default=str)
            data_size = len(json_data.encode('utf-8'))
            # logger.info(f"[업로드 시작] 키: {key}, 크기: {data_size:,} bytes")
            
            # S3 비동기 업로드
            async with self.session.client('s3',
                aws_access_key_id=Config.AWS_ACCESS_KEY_ID,
                aws_secret_access_key=Config.AWS_SECRET_ACCESS_KEY,
                region_name=Config.AWS_REGION
            ) as s3:
                response = await s3.put_object(
                    Bucket=self.bucket_name,
                    Key=key,
                    Body=json_data.encode('utf-8'),
                    ContentType='application/json',
                    ContentEncoding='utf-8'
                )
                
                if response and response.get('ResponseMetadata', {}).get('HTTPStatusCode') == 200:
                    # logger.info(f"[업로드 완료] 키: {key}, ETag: {response.get('ETag')}")
                    return response
                
        except Exception as e:
            logger.error(f"[업로드 실패] 키: {key}, 에러: {str(e)}")
            raise

    async def process_category(self, category: str, messages: List[Any], retry_count=0):
        """카테고리별 메시지 처리 및 S3 업로드
        
        Args:
            category (str): 뉴스 카테고리
            messages (List[Any]): 처리할 메시지 리스트
            retry_count (int): 현재 재시도 횟수
        """
        try:
            total_messages = len(messages)
            logger.info(f"\n{'='*50}")
            logger.info(f"[카테고리 처리 시작] {category}")
            logger.info(f"처리할 메시지 수: {total_messages}개")
            logger.info(f"{'='*50}")
            
            # 각 메시지의 업로드 태스크 생성
            upload_tasks = []
            for i, message in enumerate(messages, 1):
                message_data = message.value
                timestamp = int(time.time())
                key = self._get_s3_key(category, f"{timestamp}_{i}")
                
                # 진행 상황 로깅
                # logger.info(f"[{category}] 메시지 {i}/{total_messages} 처리 중...")
                
                # 업로드 태스크 생성
                task = self._upload_to_s3(key, [message_data])
                upload_tasks.append(task)
            
            # 모든 업로드 태스크 동시 실행
            logger.info(f"[{category}] {len(upload_tasks)}개 업로드 태스크 실행 중...")
            responses = await asyncio.gather(*upload_tasks)
            
            # 성공한 업로드 수 계산
            success_count = sum(1 for r in responses if r and r.get('ResponseMetadata', {}).get('HTTPStatusCode') == 200)
            
            logger.info(f"\n{'='*50}")
            logger.info(f"[카테고리 처리 완료] {category}")
            logger.info(f"성공: {success_count}개")
            logger.info(f"실패: {total_messages - success_count}개")
            logger.info(f"{'='*50}\n")
            
            return success_count
            
        except Exception as e:
            logger.error(f"[카테고리 처리 실패] {category}: {str(e)}")
            
            # 재시도 로직
            if retry_count < self.max_retries:
                retry_count += 1
                logger.info(f"[재시도] {category} 카테고리 처리 재시도 중... ({retry_count}/{self.max_retries})")
                await asyncio.sleep(self.retry_delay)
                return await self.process_category(category, messages, retry_count)
            else:
                logger.error(f"[최대 재시도 횟수 초과] {category} 카테고리 처리를 건너뜁니다.")
                return 0

    async def process_messages(self, run_once=False, wait_empty_timeout=10):
        """Kafka 메시지 처리 및 S3 업로드
        
        Args:
            run_once (bool): True이면 모든 메시지 처리 후 종료
            wait_empty_timeout (int): 새 메시지 확인을 위해 대기하는 시간(초)
        """
        try:
            logger.info("\n=== 메시지 처리 시작 ===")
            logger.info("모든 카테고리의 메시지를 비동기적으로 처리합니다.")
            if run_once:
                logger.info("모든 메시지 처리 후 종료합니다.")
            logger.info("=======================\n")
            
            empty_poll_count = 0
            max_empty_polls = wait_empty_timeout  # 연속 empty poll 횟수
            
            while True:
                # Kafka에서 메시지 배치 가져오기
                message_batch = self.consumer.poll(timeout_ms=1000)
                
                if message_batch:
                    # 메시지를 받았으므로 empty_poll_count 초기화
                    empty_poll_count = 0
                    
                    logger.info("\n=== 새로운 메시지 배치 수신 ===")
                    
                    # 카테고리별로 메시지 그룹화
                    category_messages = {}
                    total_messages = 0
                    
                    for topic_partition, messages in message_batch.items():
                        if not messages:
                            continue
                            
                        category = topic_partition.topic.split('.')[1]
                        if category not in category_messages:
                            category_messages[category] = []
                        
                        category_messages[category].extend(messages)
                        msg_count = len(messages)
                        total_messages += msg_count
                        logger.info(f"- {category}: {msg_count}개 메시지")
                    
                    logger.info(f"총 처리할 메시지: {total_messages}개\n")
                    
                    # 각 카테고리별 처리 태스크 생성 및 실행
                    category_tasks = [
                        self.process_category(category, messages)
                        for category, messages in category_messages.items()
                    ]
                    
                    # 모든 카테고리 동시 처리
                    if category_tasks:
                        success_counts = await asyncio.gather(*category_tasks)
                        total_success = sum(success_counts)
                        
                        logger.info(f"\n=== 배치 처리 완료 ===")
                        logger.info(f"처리된 카테고리: {len(category_tasks)}개")
                        logger.info(f"처리된 메시지: {total_messages}개")
                        logger.info(f"성공적으로 처리된 메시지: {total_success}개")
                        logger.info("=====================\n")
                    
                    # 커밋
                    self.consumer.commit()
                    logger.info("Kafka 오프셋 커밋 완료")
                    
                else:
                    logger.info("처리할 메시지 없음. 1초 후 다시 확인...")
                    
                    # run_once 모드에서 빈 폴링 횟수 카운트
                    if run_once:
                        empty_poll_count += 1
                        logger.info(f"연속 빈 폴링: {empty_poll_count}/{max_empty_polls}")
                        
                        # 지정된 시간 동안 새 메시지가 없으면 종료
                        if empty_poll_count >= max_empty_polls:
                            logger.info(f"\n=== {wait_empty_timeout}초 동안 새 메시지 없음 ===")
                            logger.info("모든 메시지 처리 완료. 프로그램을 종료합니다.")
                            return
                
                await asyncio.sleep(1)  # 매 루프마다 1초 대기

        except Exception as e:
            logger.error(f"메시지 처리 중 오류 발생: {str(e)}")
            # 최상위 오류는 그대로 전파하여 main 함수에서 처리
            raise
    
    def close(self):
        """리소스 정리"""
        logger.info("S3 저장 관리자 종료 중...")
        self.consumer.close()
        self.executor.shutdown()
        logger.info("모든 리소스가 정리되었습니다.")

async def main():
    """메인 실행 함수"""
    import argparse
    parser = argparse.ArgumentParser(description='S3 저장 관리자')
    parser.add_argument('--run-once', action='store_true', help='모든 메시지 처리 후 종료')
    parser.add_argument('--wait-empty', type=int, default=30, help='모든 메시지 처리 후 추가 대기 시간(초)')
    parser.add_argument('--max-retries', type=int, default=None, help='처리 실패 시 최대 재시도 횟수')
    parser.add_argument('--retry-delay', type=int, default=None, help='재시도 간 대기 시간(초)')
    args = parser.parse_args()
    
    storage = S3StorageManager(max_retries=args.max_retries, retry_delay=args.retry_delay)
    try:
        await storage.process_messages(run_once=args.run_once, wait_empty_timeout=args.wait_empty)
    except KeyboardInterrupt:
        logger.info("사용자에 의해 프로그램이 중단되었습니다.")
    except Exception as e:
        logger.error(f"치명적인 오류 발생: {str(e)}")
        raise
    finally:
        storage.close()

if __name__ == "__main__":
    asyncio.run(main()) 