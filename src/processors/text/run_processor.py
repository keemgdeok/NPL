import argparse
from .processor import TextProcessor

def main():
    parser = argparse.ArgumentParser(description='네이버 뉴스 텍스트 처리기')
    parser.add_argument('--mode', choices=['stream'], default='stream',
                      help='처리 모드 선택 (stream: 실시간)')
    parser.add_argument('--run-once', action='store_true',
                      help='한 번만 메시지를 처리하고 종료 (스트림 모드에서만 적용)')
    
    args = parser.parse_args()
    
    processor = TextProcessor()
    
    try:
        if args.mode == 'stream':
            print("Starting stream processing...")
            if args.run_once:
                processor.process_stream_once()
            else:
                processor.process_stream()
            
    except KeyboardInterrupt:
        print("\nProcessing interrupted by user")
    except Exception as e:
        print(f"Error during processing: {str(e)}")
    finally:
        processor.close()

if __name__ == "__main__":
    main() 