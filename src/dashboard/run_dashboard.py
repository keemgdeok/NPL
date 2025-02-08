import streamlit.cli as stcli
import sys
import os

if __name__ == "__main__":
    # 현재 디렉토리를 파이썬 경로에 추가
    current_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    sys.path.append(current_dir)
    
    # Streamlit 실행
    sys.argv = ["streamlit", "run", os.path.join(os.path.dirname(__file__), "main.py")]
    sys.exit(stcli.main()) 