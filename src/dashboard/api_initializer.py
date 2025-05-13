import streamlit as st
from .api_client import APIClient

@st.cache_resource
def get_api_client() -> APIClient:
    """
    API 클라이언트 인스턴스를 생성하고 캐싱합니다.
    모든 페이지에서 동일한 API 클라이언트 인스턴스를 사용할 수 있도록 합니다.
    
    Returns:
        APIClient: 캐싱된 API 클라이언트 인스턴스
    """
    return APIClient()

def clear_api_cache() -> None:
    """
    API 클라이언트 캐시를 초기화합니다.
    데이터가 업데이트되었을 때 호출할 수 있습니다.
    """
    # API 클라이언트 인스턴스 캐시 비우기
    get_api_client.clear()
    
    # API 메서드 캐시 비우기
    api_client = get_api_client()
    api_client.clear_cache()
    
    st.success("API 캐시가 초기화되었습니다. 최신 데이터가 로드됩니다.") 