import streamlit as st

from ui_helpers import backend_healthy
from ui_theme import apply_theme, sidebar_connectivity, workspace_header

st.set_page_config(page_title="Script Executor", page_icon="⚡", layout="wide")
apply_theme()

pages = [
    st.Page("pages/1_Dashboard.py", title="Dashboard", icon=":material/dashboard:", default=True),
    st.Page("pages/2_Run_Script.py", title="Run Script", icon=":material/play_circle:"),
    st.Page("pages/5_Dataset_Health.py", title="Dataset Health", icon=":material/fact_check:"),
    st.Page("pages/3_Execution_History.py", title="Execution History", icon=":material/history:"),
    st.Page("pages/4_Run_Details.py", title="Run Details", icon=":material/description:"),
]
navigation = st.navigation(pages, position="hidden")
workspace_header(pages[0])
with st.sidebar.container(key="workspace_navigation"):
    for page in pages:
        key = "workspace_link_active" if page == navigation else f"workspace_link_{page.url_path}"
        with st.container(key=key):
            st.page_link(page, width="stretch")
if navigation.title != "Dashboard":
    sidebar_connectivity(backend_healthy())
navigation.run()
