import argparse
from news_collector import NewsCollector

def main():
    parser = argparse.ArgumentParser(description='네이버 뉴스 수집기')
    parser.add_argument('--category', type=str, help='수집할 카테고리 (미지정시 전체 카테고리)')
    parser.add_argument('--use-api', action='store_true', help='API 사용 여부 (기본: 스크래핑)')
    parser.add_argument('--days-ago', type=int, default=1, help='몇 일 전 뉴스부터 수집할지 (기본: 1)')
    
    args = parser.parse_args()
    
    collector = NewsCollector()
    
    try:
        if args.category:
            print(f"Collecting news for category: {args.category}")
            collector.collect_news(args.category, args.use_api, args.days_ago)
        else:
            print("Collecting news for all categories")
            collector.collect_all_categories(args.use_api, args.days_ago)
            
    except KeyboardInterrupt:
        print("\nCollection interrupted by user")
    except Exception as e:
        print(f"Error during collection: {str(e)}")
    finally:
        collector.close()

if __name__ == "__main__":
    main() 