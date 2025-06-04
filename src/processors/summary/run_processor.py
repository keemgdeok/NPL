import argparse
import yaml # PyYAML import
import logging
import os
from typing import Dict, Any

from .processor import SummaryProcessor
# from ...collectors.utils.config import Config as NCloudConfig # NCloudConfig 의존성 제거
import torch

# 기본 설정 파일 경로 (실제 파일 위치에 맞게 수정)
DEFAULT_CONFIG_PATH = "src/processors/summary/summary_config.yaml"

def setup_logging(log_level_str: str = 'INFO'):
    """Sets up logging with the specified log level."""
    numeric_level = getattr(logging, log_level_str.upper(), None)
    if not isinstance(numeric_level, int):
        print(f"Warning: Invalid log level '{log_level_str}'. Defaulting to INFO.")
        numeric_level = logging.INFO
    
    logging.basicConfig(
        level=numeric_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    return logging.getLogger("summary-run-processor")

def load_config(config_path: str) -> Dict[str, Any]:
    """지정된 경로의 YAML 설정 파일을 로드합니다."""
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        if config is None:
            print(f"Warning: 설정 파일 '{config_path}'이 비어있거나 YAML 내용이 없습니다.")
            return {}
        return config
    except FileNotFoundError:
        print(f"Error: 설정 파일을 찾을 수 없습니다: '{config_path}'")
        raise
    except yaml.YAMLError as e:
        print(f"Error: YAML 설정 파일을 파싱할 수 없습니다 '{config_path}': {e}")
        raise
    except Exception as e:
        print(f"Error: 설정 파일 로드 중 예상치 못한 오류 발생 '{config_path}': {e}")
        raise

def main():
    parser = argparse.ArgumentParser(description='뉴스 기사 요약 처리기 (설정 파일 기반)')
    
    parser.add_argument('--config', type=str, default=DEFAULT_CONFIG_PATH,
                      help=f'설정 파일 경로. 기본값: {DEFAULT_CONFIG_PATH}')
    parser.add_argument('--list-topics', action='store_true',
                      help='설정 파일 기반으로 처리 가능한 Kafka 토픽 목록 출력')
    # CLI로 특정 파라미터 오버라이드 기능 추가 시 여기에 정의 (예: --run-mode, --log-level 등)

    args = parser.parse_args()

    # 설정 파일 로드
    try:
        app_config = load_config(args.config)
        if not app_config: # 설정 파일이 비어있거나 로드에 실패한 경우 (load_config에서 {} 반환)
            print("Error: 설정 내용이 비어있어 프로그램을 시작할 수 없습니다.")
            return
    except Exception:
        # load_config 내부에서 이미 오류 로깅/print, 여기서는 프로그램 종료
        return 

    # 로그 레벨 설정 (설정 파일 값 사용, 없으면 INFO)
    # CLI 오버라이드가 있다면 여기서 app_config 값을 덮어쓸 수 있음
    log_level_config = app_config.get('log_level', 'INFO')
    logger = setup_logging(log_level_config)
    logger.info(f"설정 파일 '{args.config}' 로드 완료.")

    if args.list_topics:
        kafka_settings = app_config.get('kafka_settings', {})
        topic_prefix = kafka_settings.get('topic_prefix')
        available_categories = kafka_settings.get('available_categories', {})
        
        if not topic_prefix or not available_categories:
            logger.error("설정 파일에서 'kafka_settings.topic_prefix' 또는 'kafka_settings.available_categories'를 찾을 수 없습니다.")
            return
            
        print(f"\n사용 가능한 Kafka 토픽 목록 (설정 파일 기반: '{args.config}'):")
        print("=" * 70)
        print(f"토픽 접두사: {topic_prefix}")
        print("\n입력 토픽 (*.processed):")
        if available_categories:
            for category_key, category_name in available_categories.items():
                print(f"  - {topic_prefix}.{category_key}.processed  ({category_name})")
        else:
            print("  (설정된 카테고리 없음)")
        print("\n출력 토픽 (*.summary):")
        if available_categories:
            for category_key, category_name in available_categories.items():
                print(f"  - {topic_prefix}.{category_key}.summary    ({category_name})")
        else:
             print("  (설정된 카테고리 없음)")
        print("=" * 70)
        return
    
    processor = None
    try:
        # 실행 모드 결정 (설정 파일 우선, CLI 오버라이드 가능하도록 확장 가능)
        run_mode = app_config.get('run_mode', 'stream') 
        model_path_config = app_config.get('model_path') # 설정 파일에서 모델 경로

        # 모델 경로 유효성 검사
        model_to_use = None # 기본적으로 None (TextSummarizer 내부 기본 모델 사용)
        if model_path_config:
            # model_path_config가 문자열 경로인지 먼저 확인
            if isinstance(model_path_config, str):
                model_json_config_path = os.path.join(model_path_config, "config.json")
                if os.path.exists(model_path_config) and os.path.isdir(model_path_config) and os.path.exists(model_json_config_path):
                    logger.info(f"로컬 모델 경로 사용 (설정 파일 지정): {model_path_config}")
                    model_to_use = model_path_config
                else:
                    logger.warning(f"설정 파일에 지정된 로컬 모델 경로({model_path_config})가 유효하지 않거나 config.json을 찾을 수 없습니다. TextSummarizer의 기본 모델을 사용합니다.")
            else:
                logger.warning(f"설정 파일의 model_path ('{model_path_config}')가 유효한 경로 문자열이 아닙니다. TextSummarizer의 기본 모델을 사용합니다.")
        else:
            logger.info("로컬 모델 경로가 설정 파일에 지정되지 않았습니다. TextSummarizer의 기본 모델을 사용합니다.")
        
        device_info = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
        logger.info(f"뉴스 기사 요약 시작 (디바이스: {device_info}, 실행 모드: {run_mode})")
        
        # SummaryProcessor 초기화 시 app_config와 함께 검증된 model_to_use를 model_path_override로 전달
        processor = SummaryProcessor(app_config=app_config, model_path_override=model_to_use)

        if run_mode == 'stream':
            logger.info(f"스트림 처리 모드 시작...")
            # SummaryProcessor.__init__에서 stream 관련 설정을 이미 로드함.
            # 여기서 stream_settings를 다시 읽어 processor.process_stream()에 전달할 필요 없음.
            # processor.process_stream()는 내부적으로 self.stream_idle_timeout_sec 등을 사용.
            processor.process_stream()

        elif run_mode == 'batch':
            logger.info(f"배치 처리 모드 시작 - Kafka 토픽 처음부터 읽기...")
            # SummaryProcessor.__init__에서 batch 관련 설정을 이미 로드함.
            # process_batch 호출 시 category_override 등 필요한 경우에만 CLI 인자 등을 통해 전달 가능.
            # 현재는 CLI 오버라이드가 없으므로, processor 내부 설정에 따름.
            
            # batch_processing_size는 process_batch의 인자로 여전히 받을 수 있으므로,
            # 설정 파일에서 가져와서 전달하거나, CLI 인자로 받아서 전달할 수 있음.
            # 여기서는 설정 파일의 batch_processing_size를 사용하도록 함.
            batch_settings = app_config.get('kafka_batch_settings', {})
            batch_proc_size_from_config = batch_settings.get('batch_processing_size', 100) # 기본값 100
            
            processor.process_batch(batch_processing_size=batch_proc_size_from_config)
        else:
            logger.error(f"알 수 없는 실행 모드입니다: '{run_mode}'. 설정 파일의 'run_mode'를 확인해주세요.")
            
    except KeyboardInterrupt:
        logger.info("사용자에 의해 처리가 중단되었습니다")
    except ValueError as ve:
        logger.critical(f"설정 또는 실행 준비 중 오류 발생: {ve}", exc_info=True)
    except RuntimeError as rte:
        logger.critical(f"Kafka 연결 또는 처리 중 심각한 런타임 오류 발생: {rte}", exc_info=True)
    except Exception as e:
        logger.critical(f"처리 중 예상치 못한 오류 발생: {e}", exc_info=True)
    finally:
        if processor is not None:
            try:
                logger.info("리소스 정리 중...")
                processor.close()
                logger.info("리소스 정리 완료")
            except Exception as cleanup_error:
                logger.error(f"리소스 정리 중 오류 발생: {str(cleanup_error)}", exc_info=True)
        
        logger.info("처리 완료")

if __name__ == "__main__":
    main() 