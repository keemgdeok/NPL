from typing import Dict, Any, List, Optional
from datetime import datetime
import json
from kafka import KafkaConsumer, KafkaProducer
import logging
import time
from .summarizer import TextSummarizer, MIN_TEXT_LENGTH_FOR_SUMMARY, DEFAULT_MODEL_NAME as SUMMARIZER_DEFAULT_MODEL_FALLBACK
# from ...collectors.utils.config import Config as NCloudConfig # NCloudConfig 의존성 제거

logger = logging.getLogger("summary-processor")

# 설정 파일에서 로드할 기본값들에 대한 주석 (코드 내 하드코딩된 기본값 최소화)
# 이 값들은 summary_config.yaml 파일에 정의되어 있어야 함.
# 만약 YAML 파일에 해당 키가 없을 경우, 이 값들이 사용될 수 있으나,
# YAML 파일에 명시적으로 모든 설정을 정의하는 것을 권장.

# TextSummarizer 및 SummaryProcessor 요약 파라미터 기본값 (YAML 우선)
# DEFAULT_PROCESSOR_INPUT_MAX_LEN = 1024 (summary_config.yaml -> summary_parameters.input_max_length)
# DEFAULT_PROCESSOR_SUMMARY_MIN_LEN = 30 (summary_config.yaml -> summary_parameters.summary_min_length)
# DEFAULT_PROCESSOR_SUMMARY_MAX_LEN = 150 (summary_config.yaml -> summary_parameters.summary_max_length)
# DEFAULT_PROCESSOR_NUM_BEAMS = 4 (summary_config.yaml -> summary_parameters.num_beams)
# DEFAULT_PROCESSOR_DO_SAMPLE = False (summary_config.yaml -> summary_parameters.do_sample)

# Kafka 기본 설정 (YAML 우선)
# DEFAULT_KAFKA_BOOTSTRAP_SERVERS = "localhost:9092" (summary_config.yaml -> kafka_settings.bootstrap_servers)
# DEFAULT_KAFKA_TOPIC_PREFIX = "news" (summary_config.yaml -> kafka_settings.topic_prefix)
# DEFAULT_KAFKA_GROUP_ID_STREAM = "summary-processor-group-default" (summary_config.yaml -> kafka_stream_settings.group_id)

# 메시지 관련 상수
SKIPPED_BY_PROCESSOR_MODEL_NAME = "N/A (skipped by processor)"
DEFAULT_MODEL_TYPE_INFO = "korean text summarization (T5 based)" # 모델 타입 정보 (필요시 설정에서 관리)
STREAM_CONSUMER_POLL_TIMEOUT_MS = 100 # 스트림 컨슈머 poll 타임아웃

class SummaryProcessor:
    """
    뉴스 기사 요약 처리기 클래스.
    Kafka로부터 기사 데이터를 수신하여 요약하고, 결과를 다시 Kafka로 전송합니다.
    스트리밍 및 배치 처리 모드를 지원합니다.
    """
    def __init__(self,
                 app_config: Dict[str, Any],
                 model_path_override: Optional[str] = None
                 ):
        """
        SummaryProcessor 인스턴스를 초기화합니다.

        Args:
            app_config (Dict[str, Any]): 전체 애플리케이션 설정 (summary_config.yaml 내용).
            model_path_override (Optional[str]): 로컬 모델 경로를 오버라이드합니다.
                                               None이면 설정 파일의 model_path 또는
                                               TextSummarizer의 기본 모델을 사용합니다.
        """
        self.app_config = app_config # 나중에 다른 설정에 접근할 경우를 위해 저장

        # --- 로깅 설정 (app_config 기반으로 루트 로거 설정은 외부에서 수행 가정) ---
        # 여기서 직접 로거 레벨을 설정하기보다는, main이나 run_processor.py에서
        # app_config['log_level']을 읽어 logging.basicConfig 등으로 전역 설정 권장.
        # logger.setLevel(app_config.get('log_level', "INFO").upper())

        # --- Kafka 기본 설정 로드 ---
        kafka_global_settings = app_config.get('kafka_settings', {})
        self.kafka_bootstrap_servers = kafka_global_settings.get('bootstrap_servers')
        self.kafka_topic_prefix = kafka_global_settings.get('topic_prefix')
        self.available_categories: Dict[str, str] = kafka_global_settings.get('available_categories', {})

        if not self.kafka_bootstrap_servers:
            logger.error("필수 Kafka 설정 'kafka_settings.bootstrap_servers'가 누락되었습니다.")
            raise ValueError("Kafka bootstrap servers not configured in kafka_settings")
        if not self.kafka_topic_prefix: # 토픽 접두사도 필수로 간주
            logger.error("필수 Kafka 설정 'kafka_settings.topic_prefix'가 누락되었습니다.")
            raise ValueError("Kafka topic prefix not configured in kafka_settings")
        if not self.available_categories:
            logger.error("필수 Kafka 설정 'kafka_settings.available_categories'가 누락되었거나 비어있습니다.")
            raise ValueError("Available categories not configured in kafka_settings")

        # --- 요약 파라미터 로드 ---
        summary_params_config = app_config.get('summary_parameters', {})
        
        # TextSummarizer 생성 시 사용할 모델 이름 및 경로 결정
        # model_path_override는 run_processor.py 등 외부에서 app_config['model_path']를
        # 고려하여 설정되었으므로, 여기서는 model_path_override 값을 직접 사용합니다.
        # model_path_override가 None이면, 설정 파일의 default_model_name 또는 TextSummarizer 내부 기본 모델 사용.
        text_summarizer_model_name = summary_params_config.get('default_model_name', SUMMARIZER_DEFAULT_MODEL_FALLBACK)
        
        self.summarizer = TextSummarizer(
            model_name=text_summarizer_model_name,
            model_path=model_path_override # 외부에서 검증/결정된 경로 또는 None
        )
        
        # 요약 생성 관련 파라미터 (TextSummarizer.generate 호출 시 사용)
        self.input_max_length = summary_params_config.get('input_max_length', 1024) # YAML에 없으면 사용할 기본값
        self.summary_min_length = summary_params_config.get('summary_min_length', 30)
        self.summary_max_length = summary_params_config.get('summary_max_length', 150)
        self.num_beams = summary_params_config.get('num_beams', 4)
        self.do_sample = summary_params_config.get('do_sample', False)
        
        # TextSummarizer.generate()에 전달될 추가적인 kwargs
        # 설정 파일의 summary_parameters에서 위에서 명시적으로 사용한 키들을 제외한 나머지
        self.summarizer_extra_generate_kwargs = {
            k: v for k, v in summary_params_config.items()
            if k not in ['default_model_name', 'input_max_length',
                          'summary_min_length', 'summary_max_length',
                          'num_beams', 'do_sample']
        }

        # MIN_TEXT_LENGTH_FOR_SUMMARY 값도 설정에서 관리 가능하도록 변경
        # TextSummarizer의 MIN_TEXT_LENGTH_FOR_SUMMARY를 사용하되, 설정으로 오버라이드 가능하게
        self.min_text_length_for_summary = summary_params_config.get(
            'min_text_length_for_summary_override', 
            MIN_TEXT_LENGTH_FOR_SUMMARY # TextSummarizer의 기본값 사용
        )


        # --- Kafka 스트리밍 설정 로드 ---
        kafka_stream_settings = app_config.get('kafka_stream_settings', {})
        self.stream_categories_keys: Optional[List[str]] = kafka_stream_settings.get('categories') # null이면 전체
        self.stream_group_id = kafka_stream_settings.get('group_id', f"summary-processor-group-{self.kafka_topic_prefix}-default")
        self.stream_idle_timeout_sec = kafka_stream_settings.get('idle_timeout_sec', 60)
        self.stream_gpu_batch_size = kafka_stream_settings.get('gpu_batch_size', 8)
        self.stream_gpu_batch_timeout_sec = kafka_stream_settings.get('gpu_batch_timeout_sec', 5)
        self.stream_consumer_request_timeout_ms = kafka_stream_settings.get('consumer_request_timeout_ms', 15000)

        self._configure_stream_topics_and_consumer()


        # --- Kafka 배치 처리 설정 로드 ---
        # process_batch 메서드에서 인자로도 받을 수 있지만, 기본 설정을 여기서 로드
        kafka_batch_settings = app_config.get('kafka_batch_settings', {})
        self.batch_default_category: Optional[str] = kafka_batch_settings.get('category') # null이면 스트림 또는 전체
        self.batch_read_timeout_ms = kafka_batch_settings.get('read_timeout_ms', 10000)
        self.batch_consumer_request_timeout_ms = kafka_batch_settings.get('consumer_request_timeout_ms', 15000)
        # batch_processing_size는 process_batch 메서드의 인자로 계속 받거나, 여기서 설정할 수도 있음
        # 여기서는 메서드 인자로 유지 (유연성)


        # --- Kafka Producer 설정 ---
        # 기본 Producer 설정값
        default_producer_config = {
            'bootstrap_servers': self.kafka_bootstrap_servers,
            'value_serializer': lambda x: json.dumps(x).encode('utf-8'),
            'request_timeout_ms': 30000,
            'max_block_ms': 30000,
            'api_version_auto_timeout_ms': 30000, # Kafka < 0.10 호환성 위해 필요할 수 있음
            'retries': 5,
            'retry_backoff_ms': 1000
        }
        # 설정 파일의 kafka_producer_override 값으로 기본값을 덮어쓰기
        producer_override_config = app_config.get('kafka_producer_override', {})
        final_producer_config = {**default_producer_config, **producer_override_config}

        try:
            self.producer = KafkaProducer(**final_producer_config)
        except Exception as e:
            logger.error(f"Kafka 프로듀서 생성 실패: {e}", exc_info=True)
            raise RuntimeError(f"Failed to create Kafka producer: {e}") from e

        logger.info(f"SummaryProcessor 초기화 완료. Kafka Group ID (Stream): {self.stream_group_id}")

    def _configure_stream_topics_and_consumer(self) -> None:
        """스트리밍 대상 토픽을 결정하고 Kafka 컨슈머를 생성합니다."""
        if self.stream_categories_keys is None: # 설정에서 'categories'가 null이거나 정의되지 않은 경우
            # 전체 available_categories 사용
            self.stream_processed_topics = [
                f"{self.kafka_topic_prefix}.{category_key}.processed"
                for category_key in self.available_categories.keys()
            ]
        elif isinstance(self.stream_categories_keys, list):
            # 설정에 명시된 카테고리만 사용
            self.stream_processed_topics = [
                f"{self.kafka_topic_prefix}.{cat_key}.processed"
                for cat_key in self.stream_categories_keys if cat_key in self.available_categories
            ]
            if not self.stream_processed_topics and self.stream_categories_keys:
                logger.warning(
                    f"설정 파일의 kafka_stream_settings.categories에 지정된 카테고리 키 "
                    f"{self.stream_categories_keys}가 available_categories에 유효한 항목이 없습니다."
                )
        else:
            logger.warning(
                f"설정 파일의 kafka_stream_settings.categories 형식이 잘못되었거나 (list여야 함) 유효하지 않습니다. "
                f"전체 available_categories ({list(self.available_categories.keys())}) 기반으로 구독합니다."
            )
            self.stream_processed_topics = [
                f"{self.kafka_topic_prefix}.{category_key}.processed"
                for category_key in self.available_categories.keys()
            ]

        if not self.stream_processed_topics:
            logger.warning("구독할 스트리밍 토픽이 없습니다. 카테고리 설정을 확인해주세요.")
            # Topic이 없으면 Consumer 생성 시 에러 발생하므로, 빈 리스트라도 전달
            # 또는 여기서 에러를 발생시켜 프로세서 시작을 막을 수도 있음
            # self.stream_consumer = None # 또는 더 강력한 처리

        try:
            # stream_processed_topics가 비어있더라도 KafkaConsumer는 생성 가능 (구독 토픽이 없을 뿐)
            self.stream_consumer = KafkaConsumer(
                *(self.stream_processed_topics or []), # 빈 리스트면 아무것도 구독 안함
                bootstrap_servers=self.kafka_bootstrap_servers,
                value_deserializer=lambda x: json.loads(x.decode('utf-8')),
                auto_offset_reset='latest',
                enable_auto_commit=True, # 스트림 모드에서는 자동 커밋 사용 가능
                group_id=self.stream_group_id,
                request_timeout_ms=self.stream_consumer_request_timeout_ms
            )
            logger.info(f"Kafka 스트림 컨슈머 생성 완료. 구독 토픽: {self.stream_processed_topics}, Group ID: {self.stream_group_id}")
        except Exception as e:
            logger.error(f"Kafka 스트림 컨슈머 생성 실패 (Group ID: {self.stream_group_id}, Topics: {self.stream_processed_topics}): {e}", exc_info=True)
            # 이 경우 프로세서가 정상 동작하기 어려우므로 예외를 다시 발생시키거나, 상태 플래그 설정 고려
            raise RuntimeError(f"Failed to create Kafka stream consumer: {e}") from e
    
    def _build_processed_article_message(
        self,
        original_article_data: Dict[str, Any],
        summary_result: Dict[str, Any],
        content_to_summarize: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        요약 결과 또는 스킵된 정보를 바탕으로 Kafka 메시지 페이로드를 구성합니다.

        Args:
            original_article_data (Dict[str, Any]): 원본 기사 데이터.
            summary_result (Dict[str, Any]): TextSummarizer의 요약 결과 또는 스킵 정보.
            content_to_summarize (Optional[str]): 요약 대상이었던 원본 콘텐츠 (스킵된 경우 사용).

        Returns:
            Dict[str, Any]: Kafka로 전송될 최종 메시지 페이로드.
        """
        final_data = original_article_data.copy()
        
        # summary_result에 model_name_used가 없거나, 특정 값(SKIPPED_BY_PROCESSOR_MODEL_NAME 등)으로 스킵 판별
        # 또는 processing_time_seconds가 0인 경우 (summarizer.py에서 스킵 시 이렇게 설정할 수 있음)
        is_skipped_by_summarizer = "N/A" in summary_result.get("model_name_used", "")
        is_skipped_by_processor = summary_result.get("model_name_used") == SKIPPED_BY_PROCESSOR_MODEL_NAME
        is_processing_time_zero = summary_result.get("processing_time_seconds", -1) == 0.0

        if is_skipped_by_processor or (is_skipped_by_summarizer and is_processing_time_zero) :
            # 프로세서 레벨에서 스킵 (매우 짧음) 또는 summarizer가 내부적으로 스킵하고 짧은 처리 시간 반환
            original_len = len(content_to_summarize) if content_to_summarize else 0
            final_data["summary_info"] = {
                "summary": content_to_summarize if content_to_summarize else "",
                "original_length": original_len,
                "summary_length": original_len,
                "sentence_count": summary_result.get("sentence_count", self.summarizer._get_sentence_count(content_to_summarize or "")),
                "compression_ratio": 1.0,
                "model_info": {
                    "name": summary_result.get("model_name_used", SKIPPED_BY_PROCESSOR_MODEL_NAME), # 스킵 사유 명시
                    "type": "text too short, empty, or summarizer internal skip"
                },
                "processing_time_seconds": summary_result.get("processing_time_seconds", 0.0)
            }
        else:
            # 실제 요약이 수행된 경우
            summary_text = summary_result.get("summary", "")
            original_length = summary_result.get("original_length", 0)
            summary_length = summary_result.get("summary_length", len(summary_text)) # 요약문 실제 길이
            compression_ratio = (summary_length / original_length) if original_length > 0 else 0.0

            final_data["summary_info"] = {
                "summary": summary_text,
                "original_length": original_length,
                "summary_length": summary_length,
                "sentence_count": summary_result.get("sentence_count", 0),
                "compression_ratio": round(compression_ratio, 4),
                "model_info": {
                    "name": summary_result.get("model_name_used", "unknown_model"),
                    "type": DEFAULT_MODEL_TYPE_INFO # 설정 가능하게 하거나, summarizer에서 반환된 타입 사용
                },
                "processing_time_seconds": summary_result.get("processing_time_seconds", -1.0) # 실제 처리 시간
            }
        
        final_data["summary_processed_at"] = datetime.now().isoformat()
        return final_data

    def process_article(self, article_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        단일 기사 데이터를 동기적으로 요약 처리합니다. (주로 테스트 또는 외부 직접 호출용)

        Args:
            article_data (Dict[str, Any]): 처리할 기사 데이터.
                                           'processed_content' 키에 요약할 텍스트가 있어야 합니다.

        Returns:
            Dict[str, Any]: 요약 정보가 포함된 기사 데이터.
        """
        content_to_summarize = article_data.get("processed_content", "")
        
        if not content_to_summarize or len(content_to_summarize.strip()) < self.min_text_length_for_summary:
            logger.warning(
                f"요약할 processed_content가 없거나 너무 짧습니다 (길이: {len(content_to_summarize.strip())} < {self.min_text_length_for_summary}). "
                f"URL: {article_data.get('url')}"
            )
            # TextSummarizer의 스킵 로직과 유사한 결과를 직접 생성
            summary_res_skipped = {
                "summary": content_to_summarize, # 짧으면 원본 유지
                "original_length": len(content_to_summarize),
                "summary_length": len(content_to_summarize),
                "sentence_count": self.summarizer._get_sentence_count(content_to_summarize),
                "processing_time_seconds": 0.0,
                "model_name_used": SKIPPED_BY_PROCESSOR_MODEL_NAME # 프로세서 레벨 스킵 명시
            }
            return self._build_processed_article_message(article_data, summary_res_skipped, content_to_summarize)

        # 실제 요약기 호출
        summary_result_model = self.summarizer.summarize(
            text=content_to_summarize,
            input_max_length=self.input_max_length,
            summary_min_length=self.summary_min_length,
            summary_max_length=self.summary_max_length,
            num_beams=self.num_beams,
            do_sample=self.do_sample,
            **self.summarizer_extra_generate_kwargs
        )
        
        return self._build_processed_article_message(article_data, summary_result_model, content_to_summarize)

    def _process_buffered_batch(self, message_buffer: List[Dict[str, Any]]) -> None:
        """
        버퍼에 쌓인 메시지 배치를 요약 처리하고 Kafka로 발행합니다.

        Args:
            message_buffer (List[Dict[str, Any]]): 처리할 메시지 버퍼. 각 항목은
                {'original_article': 기사데이터, 'category': 카테고리키} 형태.
        """
        if not message_buffer:
            return

        start_batch_proc_time = time.time()
        logger.info(f"버퍼된 메시지 {len(message_buffer)}개 배치 처리 시작...")

        texts_to_summarize: List[str] = []
        original_indices_for_model_input: List[int] = [] # texts_to_summarize와 매핑되는 message_buffer의 인덱스

        for i, msg_bundle in enumerate(message_buffer):
            original_article = msg_bundle['original_article']
            content_to_summarize = original_article.get("processed_content", "")
            category_from_msg = msg_bundle.get('category', 'unknown_category_in_buffer')

            if not content_to_summarize or len(content_to_summarize.strip()) < self.min_text_length_for_summary:
                # 스킵 케이스: 바로 Kafka 메시지 빌드 및 전송
                logger.debug(f"배치 내 항목 스킵 (짧거나 없음): URL {original_article.get('url')}, 길이 {len(content_to_summarize.strip())}")
                summary_res_skipped = {
                    "summary": content_to_summarize,
                    "original_length": len(content_to_summarize),
                    "summary_length": len(content_to_summarize),
                    "sentence_count": self.summarizer._get_sentence_count(content_to_summarize),
                    "processing_time_seconds": 0.0,
                    "model_name_used": SKIPPED_BY_PROCESSOR_MODEL_NAME
                }
                kafka_message = self._build_processed_article_message(original_article, summary_res_skipped, content_to_summarize)
                self._send_to_kafka(kafka_message, category_from_msg)
            else:
                # 요약 대상: 리스트에 추가
                texts_to_summarize.append(content_to_summarize)
                original_indices_for_model_input.append(i) # message_buffer의 원본 인덱스 저장
        
        num_to_summarize_by_model = len(texts_to_summarize)
        if num_to_summarize_by_model > 0:
            logger.info(f"모델 요약 대상 {num_to_summarize_by_model}개에 대해 summarize_batch 호출")
            try:
                # 배치 요약 실행
                summary_results_batch = self.summarizer.summarize_batch(
                    texts=texts_to_summarize,
                    input_max_length=self.input_max_length,
                    summary_min_length=self.summary_min_length,
                    summary_max_length=self.summary_max_length,
                    num_beams=self.num_beams, 
                    do_sample=self.do_sample,
                    **self.summarizer_extra_generate_kwargs # 추가 파라미터 전달
                )
                
                # 결과 매핑 및 Kafka 발행
                for batch_i, summary_result_item in enumerate(summary_results_batch):
                    buffer_index = original_indices_for_model_input[batch_i] # 원본 message_buffer에서의 인덱스
                    original_article_from_buffer = message_buffer[buffer_index]['original_article']
                    category_from_buffer = message_buffer[buffer_index]['category']
                    content_that_was_summarized = texts_to_summarize[batch_i] # 실제 모델에 들어간 텍스트
                    
                    kafka_message = self._build_processed_article_message(
                        original_article_from_buffer, 
                        summary_result_item,
                        content_that_was_summarized
                    )
                    self._send_to_kafka(kafka_message, category_from_buffer)
            
            except Exception as e:
                logger.error(f"summarize_batch 실행 또는 결과 처리 중 심각한 오류: {e}", exc_info=True)
                # 오류 발생 시, 해당 배치 항목들에 대한 처리가 실패했음을 인지.
                # 개별적으로 실패 메시지를 보내거나, 재시도 로직 등을 고려할 수 있으나 여기서는 로깅만.
                # 실패한 항목들은 original_indices_for_model_input 와 message_buffer를 통해 식별 가능.
                for batch_i_on_error in range(num_to_summarize_by_model):
                    buffer_idx_on_error = original_indices_for_model_input[batch_i_on_error]
                    failed_article_data = message_buffer[buffer_idx_on_error]['original_article']
                    failed_category = message_buffer[buffer_idx_on_error]['category']
                    logger.error(f"요약 실패 항목(배치 오류로 인해): URL {failed_article_data.get('url')}, Category {failed_category}")
                    # 필요시 실패 이벤트 발행
                    # self._send_error_to_kafka(failed_article_data, failed_category, str(e))

        end_batch_proc_time = time.time()
        logger.info(f"버퍼된 메시지 {len(message_buffer)}개 배치 처리 완료. 소요 시간: {end_batch_proc_time - start_batch_proc_time:.2f}초")

    def process_stream(self) -> None:
        """
        Kafka 스트림에서 메시지를 지속적으로 수신하여 처리합니다.
        설정된 배치 크기(stream_gpu_batch_size) 또는 타임아웃(stream_gpu_batch_timeout_sec)에 도달하면
        버퍼링된 메시지를 일괄 처리합니다.
        idle_timeout_sec 동안 메시지가 없으면 자동 종료합니다.
        """
        if not self.stream_consumer or not self.stream_processed_topics : # 구독할 토픽이 없는 경우
            logger.warning("스트림 컨슈머가 없거나 구독할 토픽이 없어 process_stream을 시작할 수 없습니다.")
            return

        message_buffer: List[Dict[str, Any]] = [] # {'original_article': data, 'category': cat_key}
        last_message_received_time = time.time()
        last_batch_processed_time = time.time() # 버퍼가 실제로 처리된 시간
        # consumer = self.stream_consumer # 인스턴스 변수 직접 사용

        try:
            logger.info(
                f"Kafka 스트림({self.stream_group_id})에서 뉴스 데이터 수신 대기 시작...\n"
                f"  구독 토픽: {self.stream_processed_topics}\n"
                f"  GPU 배치 크기: {self.stream_gpu_batch_size}, 배치 타임아웃: {self.stream_gpu_batch_timeout_sec}초\n"
                f"  유휴 타임아웃: {self.stream_idle_timeout_sec}초"
            )
            
            while True:
                # 짧은 타임아웃으로 메시지 폴링 (거의 non-blocking)
                messages_polled = self.stream_consumer.poll(timeout_ms=STREAM_CONSUMER_POLL_TIMEOUT_MS)
                now = time.time()

                if messages_polled:
                    last_message_received_time = now # 새 메시지 수신 시간 업데이트
                    for topic_partition, partition_messages in messages_polled.items():
                        for message in partition_messages:
                            try:
                                article_data = message.value
                                # 토픽 이름에서 카테고리 키 추출
                                topic_name = message.topic
                                prefix_to_remove = f"{self.kafka_topic_prefix}."
                                suffix_to_remove = ".processed"
                                category_key = 'unknown_category_from_topic'
                                if topic_name.startswith(prefix_to_remove) and topic_name.endswith(suffix_to_remove):
                                    category_key = topic_name[len(prefix_to_remove):-len(suffix_to_remove)]
                                
                                if category_key not in self.available_categories:
                                    logger.warning(f"토픽 '{topic_name}'에서 추출된 카테고리 키 '{category_key}'가 "
                                                   f"available_categories에 없습니다. 메시지 건너뜀. URL: {article_data.get('url')}")
                                    continue
                                
                                # 'category' 필드가 이미 있다면 존중, 없다면 토픽에서 추출한 값 사용
                                if 'category' not in article_data:
                                    article_data['category'] = category_key

                                message_buffer.append({
                                    # 'original_message': message, # 배치에서는 offset 커밋 안하므로 제외 가능
                                    'original_article': article_data,
                                    'category': category_key 
                                })

                                # 배치 처리 단위 크기에 도달하면 중간 처리
                                if len(message_buffer) >= self.stream_gpu_batch_size:
                                    logger.debug(f"[Batch] 처리 단위 크기({self.stream_gpu_batch_size}) 도달. 중간 배치 처리 시작.")
                                    self._process_buffered_batch(message_buffer)
                                    message_buffer.clear()
                                    logger.debug(f"[Batch] 중간 배치 처리 완료. 현재까지 총 {len(message_buffer)}개 처리됨.")
                                
                            except json.JSONDecodeError as jde:
                                logger.error(f"[Stream] 메시지 JSON 디코딩 오류: {jde}. Topic: {message.topic}, Offset: {message.offset}", exc_info=True)
                                continue
                            except Exception as e:
                                logger.error(f"[Stream] 메시지 처리 또는 버퍼 추가 중 오류: {e}. Topic: {message.topic}, Offset: {message.offset}", exc_info=True)
                                continue
                
                # 배치 처리 조건 확인
                should_process_batch = False
                buffer_len = len(message_buffer)
                if buffer_len >= self.stream_gpu_batch_size:
                    logger.debug(f"배치 크기 도달 ({buffer_len} >= {self.stream_gpu_batch_size}). 배치 처리 준비.")
                    should_process_batch = True
                elif buffer_len > 0 and (now - last_batch_processed_time >= self.stream_gpu_batch_timeout_sec):
                    # 버퍼에 메시지가 있고, 마지막 배치 처리 후 gpu_batch_timeout_sec이 지났을 때
                    logger.debug(f"배치 타임아웃 도달 ({now - last_batch_processed_time:.2f}초 >= {self.stream_gpu_batch_timeout_sec}초). "
                                 f"버퍼 크기 {buffer_len}. 배치 처리 준비.")
                    should_process_batch = True
                
                if should_process_batch:
                    self._process_buffered_batch(message_buffer)
                    message_buffer.clear()
                    last_batch_processed_time = time.time() # 실제 배치가 처리된 시간으로 업데이트

                # 스트림 유휴 타임아웃 체크 (메시지 없는 상태 지속)
                if self.stream_idle_timeout_sec > 0 and (now - last_message_received_time > self.stream_idle_timeout_sec):
                    logger.info(f"[Stream] {self.stream_idle_timeout_sec}초 동안 새 메시지가 없어 자동 종료 준비...")
                    if message_buffer: # 종료 전 남은 버퍼 처리
                        logger.info(f"자동 종료 전 남은 메시지 {len(message_buffer)}개 처리 중...")
                        self._process_buffered_batch(message_buffer)
                        message_buffer.clear()
                    break # while 루프 종료
                    
        except KeyboardInterrupt:
            logger.info("[Stream] 사용자에 의해 처리가 중단되었습니다. 남은 버퍼 처리 시도.")
        except Exception as e:
            logger.error(f"[Stream] 처리 루프 중 예기치 않은 오류 발생: {e}", exc_info=True)
        finally:
            if message_buffer: # 루프 정상/비정상 종료 시 남은 버퍼 최종 처리
                logger.info(f"스트림 종료 전 최종 남은 메시지 {len(message_buffer)}개 처리 중...")
                self._process_buffered_batch(message_buffer)
                message_buffer.clear()
            
            logger.info("[Stream] 처리 루프 종료됨.")
            # 스트림 컨슈머는 self.close()에서 정리

    def process_batch(self,
                      category_override: Optional[str] = None,
                      read_timeout_ms_override: Optional[int] = None,
                      batch_processing_size: int = 100
                      ) -> None:
        """
        지정된 카테고리(들)의 모든 메시지를 Kafka에서 읽어 배치 처리합니다.

        카테고리 결정 우선순위:
        1. `category_override` 함수 인자 (단일 카테고리 문자열)
        2. `summary_config.yaml`의 `kafka_batch_settings.category` (단일 카테고리 문자열)
        3. `summary_config.yaml`의 `kafka_stream_settings.categories` (카테고리 리스트)
        4. `summary_config.yaml`의 `kafka_settings.available_categories` (전체 사용 가능 카테고리)

        Args:
            category_override (Optional[str]): 처리할 단일 카테고리 키를 외부에서 지정.
                                               None이면 설정 파일에 따라 결정.
            read_timeout_ms_override (Optional[int]): Kafka 컨슈머의 poll 타임아웃(ms)을 외부에서 지정.
                                                      None이면 설정 파일 값 사용.
            batch_processing_size (int): 한 번의 `_process_buffered_batch` 호출로 처리할 메시지 수.
                                         메모리 사용량 조절에 사용.
        """
        effective_category_keys_for_batch: List[str] = []

        # 1. category_override 인자 확인
        if category_override:
            if category_override in self.available_categories:
                effective_category_keys_for_batch = [category_override]
                logger.info(f"배치 처리 대상 카테고리 (인자 지정): {category_override}")
            else:
                logger.error(f"인자로 지정된 알 수 없는 카테고리입니다: {category_override}. "
                               f"유효한 카테고리: {list(self.available_categories.keys())}")
                return
        # 2. 설정 파일의 kafka_batch_settings.category 확인
        elif self.batch_default_category and self.batch_default_category in self.available_categories:
            effective_category_keys_for_batch = [self.batch_default_category]
            logger.info(f"배치 처리 대상 카테고리 (설정 kafka_batch_settings.category): {self.batch_default_category}")
        # 3. 설정 파일의 kafka_stream_settings.categories (스트림 처리 대상 카테고리) 확인
        elif self.stream_categories_keys and isinstance(self.stream_categories_keys, list):
            valid_stream_cats = [cat for cat in self.stream_categories_keys if cat in self.available_categories]
            if valid_stream_cats:
                effective_category_keys_for_batch = valid_stream_cats
                logger.info(f"배치 처리 대상 카테고리 (설정 kafka_stream_settings.categories 기반): {effective_category_keys_for_batch}")
        
        # 4. 위 조건 모두 만족 못하면, 전체 available_categories 사용
        if not effective_category_keys_for_batch:
            effective_category_keys_for_batch = list(self.available_categories.keys())
            logger.info(f"배치 처리 대상 카테고리 (전체 available_categories 기반): {effective_category_keys_for_batch}")

        if not effective_category_keys_for_batch:
            logger.warning("최종적으로 배치 처리할 대상 카테고리가 없습니다.")
            return

        batch_topics_to_consume = [
            f"{self.kafka_topic_prefix}.{cat_key}.processed" for cat_key in effective_category_keys_for_batch
        ]
        
        final_read_timeout_ms = read_timeout_ms_override if read_timeout_ms_override is not None else self.batch_read_timeout_ms
        
        logger.info(f"Kafka 배치 처리 시작. 대상 토픽: {batch_topics_to_consume}, 읽기 타임아웃: {final_read_timeout_ms}ms, 처리 단위: {batch_processing_size}")

        batch_consumer = None
        try:
            # 배치 컨슈머용 request_timeout_ms 설정 사용
            batch_consumer = KafkaConsumer(
                *batch_topics_to_consume,
                bootstrap_servers=self.kafka_bootstrap_servers,
                value_deserializer=lambda x: json.loads(x.decode('utf-8')),
                auto_offset_reset='earliest', # 처음부터 모든 메시지 처리
                enable_auto_commit=False,    # 수동으로 커밋하거나, 여기서는 읽기만 하므로 커밋 안함 (그룹 ID 없음)
                group_id=None,               # 배치 처리는 특정 그룹에 속하지 않고 독립적으로 모든 메시지 읽기
                request_timeout_ms=self.batch_consumer_request_timeout_ms
            )
            logger.info(f"배치 컨슈머 생성 완료 (읽기 시작: earliest, Group ID: None, Request Timeout: {self.batch_consumer_request_timeout_ms}ms)")
            
            processed_count_total = 0
            message_batch_for_processing: List[Dict[str, Any]] = [] # {'original_article': data, 'category': cat_key}
            
            while True:
                messages_polled = batch_consumer.poll(timeout_ms=final_read_timeout_ms)
                if not messages_polled: # 타임아웃 발생, 더 이상 메시지 없음
                    if message_batch_for_processing: 
                        logger.info(f"[Batch] Kafka 폴링 타임아웃. 남은 메시지 {len(message_batch_for_processing)}개 처리 시작.")
                        self._process_buffered_batch(message_batch_for_processing) 
                        processed_count_total += len(message_batch_for_processing)
                        message_batch_for_processing.clear()
                    logger.info(f"[Batch] {final_read_timeout_ms}ms 동안 새 메시지가 없어 처리 종료.")
                    break # while 루프 종료
                
                for topic_partition, partition_messages in messages_polled.items():
                    for message in partition_messages:
                        try:
                            article_data = message.value
                            topic_name = topic_partition.topic 
                            # 토픽 이름에서 카테고리 키 추출
                            prefix_to_remove = f"{self.kafka_topic_prefix}."
                            suffix_to_remove = ".processed"
                            category_key_from_topic = 'unknown_category_from_batch_topic'
                            if topic_name.startswith(prefix_to_remove) and topic_name.endswith(suffix_to_remove):
                                category_key_from_topic = topic_name[len(prefix_to_remove):-len(suffix_to_remove)]
                            
                            if category_key_from_topic not in self.available_categories:
                                logger.warning(f"배치 토픽 '{topic_name}'의 카테고리 '{category_key_from_topic}'가 "
                                               f"available_categories에 없습니다. 메시지 건너뜀. URL: {article_data.get('url')}")
                                continue
                            
                            # 'category' 필드가 이미 있다면 존중, 없다면 토픽에서 추출한 값 사용
                            if 'category' not in article_data:
                                article_data['category'] = category_key_from_topic

                            message_batch_for_processing.append({
                                # 'original_message': message, # 배치에서는 offset 커밋 안하므로 제외 가능
                                'original_article': article_data,
                                'category': category_key_from_topic 
                            })

                            # 배치 처리 단위 크기에 도달하면 중간 처리
                            if len(message_batch_for_processing) >= batch_processing_size:
                                logger.debug(f"[Batch] 처리 단위 크기({batch_processing_size}) 도달. 중간 배치 처리 시작.")
                                self._process_buffered_batch(message_batch_for_processing)
                                processed_count_total += len(message_batch_for_processing)
                                message_batch_for_processing.clear()
                                logger.debug(f"[Batch] 중간 배치 처리 완료. 현재까지 총 {processed_count_total}개 처리됨.")
                            
                        except json.JSONDecodeError as jde:
                            logger.error(f"[Batch] 메시지 JSON 디코딩 오류: {jde}. Topic: {message.topic}, Offset: {message.offset}", exc_info=True)
                            continue
                        except Exception as e:
                            logger.error(f"[Batch] 메시지 처리 또는 버퍼 추가 중 오류: {e}. Topic: {message.topic}, Offset: {message.offset}", exc_info=True)
                            continue
            
            logger.info(f"배치 처리 완료. 총 약 {processed_count_total}개 기사 처리 및 Kafka 발행 시도됨.")

        except Exception as e:
            logger.error(f"Kafka 배치 처리 중 심각한 오류 발생: {e}", exc_info=True)
        finally:
            if batch_consumer:
                batch_consumer.close()
                logger.info("Kafka 배치 컨슈머가 정리되었습니다.")
    
    def _send_to_kafka(self, data: Dict[str, Any], category_key: str) -> None:
        """
        처리된 요약 데이터를 해당 카테고리의 summary 토픽으로 전송합니다.

        Args:
            data (Dict[str, Any]): 전송할 데이터 (summary_info 포함).
            category_key (str): 대상 카테고리 키.
        """
        if category_key not in self.available_categories:
            logger.error(
                f"Kafka 전송 시도 중 알 수 없는 카테고리 키 '{category_key}'가 사용되었습니다. "
                f"메시지 전송 실패. URL: {data.get('url')}"
            )
            return

        try:
            # 최종 발행 토픽 이름 구성 (예: "news.economy.summary")
            target_topic = f"{self.kafka_topic_prefix}.{category_key}.summary"
            
            # Kafka Producer의 send는 비동기일 수 있으나, 여기서는 결과 콜백을 사용하지 않음.
            # 에러 발생 시 예외를 던지므로 try-except로 잡음.
            future = self.producer.send(target_topic, value=data)
            # Optional: future.get(timeout=...) 등으로 블로킹하여 전송 확인 가능하나, 성능에 영향.
            # 로깅은 debug 레벨로 변경하거나, 성공/실패에 따라 다르게 로깅.
            # logger.debug(f"Kafka 토픽 '{target_topic}'으로 데이터 전송 요청됨. URL: {data.get('url')}")
            
            # 전송 성공/실패 로깅을 위해 콜백 사용 예시 (필요시)
            # future.add_callback(self._on_send_success, topic=target_topic, url=data.get('url'))
            # future.add_errback(self._on_send_error, topic=target_topic, url=data.get('url'))

        except Exception as e:
            logger.error(f"Kafka 메시지 전송 중 오류 발생. Topic: {target_topic}, URL: {data.get('url')}, Error: {e}", exc_info=True)

    # Kafka 전송 콜백 예시 (필요하다면 사용)
    # def _on_send_success(self, record_metadata, topic: str, url: Optional[str]):
    #     logger.debug(f"메시지 성공적으로 전송됨. Topic: {topic}, Partition: {record_metadata.partition}, Offset: {record_metadata.offset}, URL: {url}")

    # def _on_send_error(self, excp, topic: str, url: Optional[str]):
    #     logger.error(f"메시지 전송 실패. Topic: {topic}, URL: {url}, Error: {excp}", exc_info=excp)


    def close(self) -> None:
        """SummaryProcessor가 사용한 리소스를 정리합니다."""
        logger.info("SummaryProcessor 리소스 정리 시작...")
        if hasattr(self, 'stream_consumer') and self.stream_consumer:
            try:
                self.stream_consumer.close()
                logger.info("Kafka 스트림 컨슈머가 성공적으로 정리되었습니다.")
            except Exception as e:
                logger.error(f"Kafka 스트림 컨슈머 정리 중 오류 발생: {e}", exc_info=True)

        # 배치 컨슈머는 process_batch 메서드 내에서 생성되고 닫히므로 여기서는 별도 처리 X

        if hasattr(self, 'producer') and self.producer:
            try:
                # 모든 메시지가 전송되도록 flush 호출 후 close
                self.producer.flush(timeout=10) # 10초 타임아웃
                logger.info("Kafka 프로듀서 flush 완료.")
            except Exception as e:
                logger.warning(f"Kafka 프로듀서 flush 중 오류 발생: {e}", exc_info=True)
            finally:
                try:
                    self.producer.close(timeout=10) # 10초 타임아웃
                    logger.info("Kafka 프로듀서가 성공적으로 정리되었습니다.")
                except Exception as e_close:
                    logger.error(f"Kafka 프로듀서 close 중 오류 발생: {e_close}", exc_info=True)
        
        # TextSummarizer 모델 리소스 정리는 TextSummarizer 클래스 내부에서 처리 (필요시)
        # if hasattr(self.summarizer, 'close'): # 만약 summarizer에 close 메서드가 있다면
        #     self.summarizer.close()

        logger.info("SummaryProcessor 리소스 정리가 완료되었습니다.")

# --- main 또는 run_processor.py 에서 사용될 예시 ---
# if __name__ == '__main__':
#     import yaml
#     # 설정 파일 로드 (실제 환경에서는 경로 관리 필요)
#     try:
#         with open("src/processors/summary/summary_config.yaml", 'r', encoding='utf-8') as f:
#             config = yaml.safe_load(f)
#     except FileNotFoundError:
#         logger.error("summary_config.yaml 파일을 찾을 수 없습니다. 기본 설정으로 실행이 불가능할 수 있습니다.")
#         # 여기서 프로그램을 종료하거나, 정말 최소한의 기본값으로 동작하도록 처리해야 함
#         # 이 예제에서는 config가 없으면 이후 processor 생성에서 오류 발생
#         config = {} 
#
#     # 로깅 기본 설정 (실제로는 더 정교하게 설정)
#     log_level_from_config = config.get('log_level', "INFO").upper()
#     logging.basicConfig(level=log_level_from_config, 
#                         format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
#
#     # 모델 경로 오버라이드 예시 (설정 파일에 model_path가 있거나, CLI 인자로 받을 수 있음)
#     # model_path_cli_arg = None # 또는 "/path/to/local_model"
#     # model_path_from_config = config.get('model_path') # YAML에 model_path가 정의되어 있다면
#     # final_model_path = model_path_cli_arg or model_path_from_config
#
#     try:
#         processor = SummaryProcessor(app_config=config) # model_path_override=final_model_path
#
#         run_mode = config.get('run_mode', 'stream') # 기본값 stream
#
#         if run_mode == "stream":
#             processor.process_stream()
#         elif run_mode == "batch":
#             # 배치 모드 시 카테고리 지정 예시 (CLI 인자나 설정으로 받을 수 있음)
#             # batch_category_arg = None # 또는 "economy"
#             # batch_category_from_config_batch_settings = config.get('kafka_batch_settings', {}).get('category')
#             # final_batch_category = batch_category_arg or batch_category_from_config_batch_settings
#             # processor.process_batch(category_override=final_batch_category, batch_processing_size=50)
#             
#             # 여기서는 설정 파일의 kafka_batch_settings.category를 우선 사용하도록 호출
#             processor.process_batch(batch_processing_size=config.get('kafka_batch_settings',{}).get('batch_processing_size', 100))
#
#         elif run_mode == "test_single_article": # 단일 기사 테스트 모드 (예시)
#             sample_article = {
#                 "url": "http://example.com/news/123",
#                 "title": "테스트 뉴스 제목",
#                 "processed_content": "이것은 매우 긴 테스트 뉴스 기사의 내용입니다. 요약 모델이 이 내용을 바탕으로 멋진 요약을 생성해주기를 바랍니다. 반복적인 내용도 좀 넣어보고, 길이를 늘려보겠습니다. 한국어 자연어 처리는 정말 재미있습니다. 이 문장은 요약에 포함될까요? 한 번 지켜봅시다. 최소 길이를 넘기기 위해 충분한 텍스트를 작성해야 합니다. 인공지능 기술은 빠르게 발전하고 있습니다."
#                 # 'category'는 process_article에서는 직접 사용하지 않지만, _send_to_kafka를 호출한다면 필요
#             }
#             # MIN_TEXT_LENGTH_FOR_SUMMARY 보다 짧은 텍스트 테스트
#             sample_article_short = {
#                  "url": "http://example.com/news/124",
#                  "title": "짧은 테스트",
#                  "processed_content": "너무 짧아요."
#             }
#             
#             result1 = processor.process_article(sample_article)
#             logger.info(f"테스트 기사 요약 결과: {json.dumps(result1, ensure_ascii=False, indent=2)}")
#             
#             result2 = processor.process_article(sample_article_short)
#             logger.info(f"짧은 테스트 기사 요약 결과: {json.dumps(result2, ensure_ascii=False, indent=2)}")
#
#         else:
#             logger.error(f"알 수 없는 실행 모드입니다: {run_mode}. 'stream' 또는 'batch'를 사용하세요.")
#
#     except ValueError as ve: # 설정 관련 에러
#         logger.critical(f"프로세서 초기화 또는 실행 준비 중 설정 오류 발생: {ve}", exc_info=True)
#     except RuntimeError as rte: # Kafka 연결 등 런타임 에러
#         logger.critical(f"프로세서 실행 중 심각한 런타임 오류 발생: {rte}", exc_info=True)
#     except Exception as e:
#         logger.critical(f"알 수 없는 예외 발생: {e}", exc_info=True)
#     finally:
#         if 'processor' in locals() and processor: # processor가 성공적으로 생성된 경우에만 close 호출
#             processor.close()

# 이 파일은 이전 코드를 기반으로 작성되었습니다. 주석 처리된 코드와 관련된 부분은 새로운 코드로 대체되었습니다. 