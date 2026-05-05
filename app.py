"""
app.py
SAP AI Platform — Main Entry Point & Home Page
"""

import streamlit as st
from utils.supabase_client import init_supabase

st.set_page_config(
    page_title="SAP AI Platform",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

with open("components/styles.css") as f:
    st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)

if "llm_provider" not in st.session_state:
    st.session_state.llm_provider = "groq"
if "active_client" not in st.session_state:
    st.session_state.active_client = None
if "active_project" not in st.session_state:
    st.session_state.active_project = None

with st.sidebar:
    st.markdown("## ⚡ SAP AI Platform")
    st.caption("v2.0 — Phase 0")
    st.divider()

    provider_labels = {
        "groq":   "🟠 Groq Llama 3.3 70B",
        "claude": "🟣 Claude Sonnet 4.6",
    }
    st.markdown(f"**LLM:** {provider_labels[st.session_state.llm_provider]}")

    if st.session_state.active_client:
        st.markdown(f"**Client:** {st.session_state.active_client}")
    if st.session_state.active_project:
        st.markdown(f"**Project:** {st.session_state.active_project}")

    st.divider()
    st.markdown("### Tools")
    st.page_link("pages/1_SAP_Data_Migration_Error_Analyzer.py",
                 label="🔧 SAP Migration Error Analyzer")
    st.page_link("pages/2_SAP_Data_Migration_Data_Quality_Checker.py",
                 label="✅ Data Quality Checker")
    st.page_link("pages/3_NL_Query.py",
                 label="📊 Datasphere NL Query")
    st.page_link("pages/4_Admin_Panel.py",
                 label="⚙️ Admin Panel")
    st.divider()
    st.caption("Built by Sparky — SAP Migration Lead")

st.markdown("""
<div class="hero">
    <h1>⚡ SAP AI Platform</h1>
    <p class="hero-sub">Three RAG-powered AI tools for SAP Data Migration & Analytics professionals</p>
</div>
""", unsafe_allow_html=True)

col1, col2, col3 = st.columns(3)

with col1:
    st.markdown("""
    <div class="tool-card tool-card--blue">
        <div class="tool-icon">🔧</div>
        <h3>Migration Error Analyzer</h3>
        <p>Diagnose SAP load errors using AI + hierarchical project memory across 8 error types.</p>
        <div class="tool-badge">Phase 1 — Active</div>
    </div>
    """, unsafe_allow_html=True)
    st.page_link("pages/1_SAP_Data_Migration_Error_Analyzer.py",
                 label="Open Error Analyzer →")

with col2:
    st.markdown("""
    <div class="tool-card tool-card--green">
        <div class="tool-icon">✅</div>
        <h3>Data Quality Checker</h3>
        <p>Score and flag data quality issues in migration extracts before loading to SAP.</p>
        <div class="tool-badge">Phase 2</div>
    </div>
    """, unsafe_allow_html=True)
    st.page_link("pages/2_SAP_Data_Migration_Data_Quality_Checker.py",
                 label="Open Quality Checker →")

with col3:
    st.markdown("""
    <div class="tool-card tool-card--purple">
        <div class="tool-icon">📊</div>
        <h3>Datasphere NL Query</h3>
        <p>Query SAP Datasphere in plain English — returns answers and interactive charts.</p>
        <div class="tool-badge">Phase 3</div>
    </div>
    """, unsafe_allow_html=True)
    st.page_link("pages/3_NL_Query.py",
                 label="Open NL Query →")

st.divider()
st.markdown("### System Status")

sc1, sc2, sc3, sc4 = st.columns(4)

with sc1:
    st.metric("LLM Provider", provider_labels[st.session_state.llm_provider])
with sc2:
    try:
        db = init_supabase()
        db_status = "🟢 Connected" if db else "🟡 Not configured"
    except Exception:
        db_status = "🔴 Error"
    st.metric("Database", db_status)
with sc3:
    st.metric("Active Client", st.session_state.active_client or "Not set")
with sc4:
    st.metric("Active Project", st.session_state.active_project or "Not set")
