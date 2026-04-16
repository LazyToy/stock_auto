import streamlit as st
import time

def render_sidebar(load_logs_func):
    """사이드바 렌더링"""
    with st.sidebar:
        st.header("System Status")
        auto_refresh = st.checkbox("Auto Refresh (30s)", value=True)
        
        st.subheader("Recent Logs")
        logs = load_logs_func(30)
        st.code("".join(logs), language="text") # 로그 뷰어
        
        if auto_refresh:
            time.sleep(1) # Rerun trigger
            st.empty() 
        
        if st.button("수동 새로고침"):
            st.cache_data.clear()
            
        return auto_refresh
