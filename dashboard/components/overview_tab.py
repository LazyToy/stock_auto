import streamlit as st

def render_overview_tab(state_kr, state_us):
    """종합(Overview) 탭 렌더링"""
    col1, col2 = st.columns(2)

    kr_asset = state_kr.get('total_asset') if state_kr else None
    us_asset = state_us.get('total_asset') if state_us else None

    with col1:
        if kr_asset is not None:
            st.metric("KR Total Asset", f"₩{int(kr_asset):,}")
        else:
            st.metric("KR Total Asset", "—")
            st.warning("데이터 없음 — 매매 시스템을 먼저 실행하세요")
        if state_kr and kr_asset is not None:
            st.success(f"Last Update: {state_kr['timestamp']}")
        elif not state_kr:
            st.warning("KR Data Not Found")

    with col2:
        if us_asset is not None:
            st.metric("US Total Asset", f"${float(us_asset):,.2f}")
        else:
            st.metric("US Total Asset", "—")
            st.warning("데이터 없음 — 매매 시스템을 먼저 실행하세요")
        if state_us and us_asset is not None:
            st.success(f"Last Update: {state_us['timestamp']}")
        elif not state_us:
            st.warning("US Data Not Found")

    # 자산 추이 그래프 — SQLite portfolio_history 테이블에서 데이터 조회
    st.subheader("자산 추이")
    try:
        import sys, os
        sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
        from src.utils.database import DatabaseManager
        import pandas as pd

        db = DatabaseManager()
        rows_kr = db.get_portfolio_history(market="KR", days=90)
        rows_us = db.get_portfolio_history(market="US", days=90)

        has_data = False
        if rows_kr:
            df_kr = pd.DataFrame(rows_kr)[['date', 'total_asset']].rename(
                columns={'total_asset': 'KR (₩)'}
            ).set_index('date').sort_index()
            has_data = True
        if rows_us:
            df_us = pd.DataFrame(rows_us)[['date', 'total_asset']].rename(
                columns={'total_asset': 'US ($)'}
            ).set_index('date').sort_index()
            has_data = True

        if has_data:
            if rows_kr and rows_us:
                df_chart = df_kr.join(df_us, how='outer')
            elif rows_kr:
                df_chart = df_kr
            else:
                df_chart = df_us
            st.line_chart(df_chart)
        else:
            st.info("자산 추이 그래프는 데이터 누적 후 제공됩니다.")
    except Exception:
        st.info("자산 추이 그래프는 데이터 누적 후 제공됩니다.")
