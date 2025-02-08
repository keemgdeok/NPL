import uvicorn
import argparse

def main():
    parser = argparse.ArgumentParser(description='네이버 뉴스 분석 API 서버')
    parser.add_argument('--host', type=str, default="0.0.0.0",
                      help='서버 호스트 (기본: 0.0.0.0)')
    parser.add_argument('--port', type=int, default=8000,
                      help='서버 포트 (기본: 8000)')
    parser.add_argument('--reload', action='store_true',
                      help='개발 모드에서 코드 변경 시 자동 재시작')
    
    args = parser.parse_args()
    
    uvicorn.run(
        "src.api.main:app",
        host=args.host,
        port=args.port,
        reload=args.reload
    )

if __name__ == "__main__":
    main() 