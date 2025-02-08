import argparse
from processor import TextProcessor

def main():
    parser = argparse.ArgumentParser(description='네이버 뉴스 텍스트 처리기')
    parser.add_argument('--mode', choices=['stream', 'batch'], default='stream',
                      help='처리 모드 선택 (stream: 실시간, batch: 배치)')
    parser.add_argument('--category', type=str,
                      help='처리할 카테고리 (배치 모드에서만 사용)')
    parser.add_argument('--days', type=int, default=1,
                      help='처리할 기간 (일 단위, 배치 모드에서만 사용)')
    
    args = parser.parse_args()
    
    processor = TextProcessor()
    
    try:
        if args.mode == 'stream':
            print("Starting stream processing...")
            processor.process_stream()
        else:
            print(f"Starting batch processing for the last {args.days} days...")
            processor.process_batch(args.category, args.days)
            
    except KeyboardInterrupt:
        print("\nProcessing interrupted by user")
    except Exception as e:
        print(f"Error during processing: {str(e)}")
    finally:
        processor.close()

if __name__ == "__main__":
    main() 