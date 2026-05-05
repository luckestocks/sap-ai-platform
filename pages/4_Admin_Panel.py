"""
pages/4_Admin_Panel.py
Admin Control Panel — LLM switch, client/project management, KB viewer, analytics.
"""

import streamlit as st
from utils.supabase_client import init_supabase

st.set_page_config(
    page_title="Admin Panel | SAP AI Platform",
    page_icon="⚙️",
    layout="wide",
)

with open("components/styles.css") as f:
    st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)

st.markdown("# ⚙️ Admin Control Panel")

db = init_supabase()
db_connected = db is not None

# ── Status bar ────────────────────────────────────────────────────────────────
s1, s2, s3 = st.columns(3)
with s1:
    st.metric("Database", "🟢 Connected" if db_connected else "🔴 Not configured")
with s2:
    provider_map = {
        "gemini": "🟢 Gemini Flash",
        "claude": "🟣 Claude Sonnet 4.6",
        "groq":   "🟠 Groq Llama 3.1",
    }
    st.metric("Active LLM", provider_map.get(st.session_state.get("llm_provider", "gemini"), "Unknown"))
with s3:
    st.metric("Active Client", st.session_state.get("active_client") or "None")

st.divider()

# ── Tabs ──────────────────────────────────────────────────────────────────────
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "🔀 LLM Config",
    "🏢 Clients & Projects",
    "👥 Team",
    "📚 Knowledge Base",
    "📈 Usage Analytics",
])

# ── Tab 1: LLM Config ─────────────────────────────────────────────────────────
with tab1:
    st.markdown("### Global LLM Switch")
    st.caption("Applies to all three tools simultaneously. No code change required.")

    current = st.session_state.get("llm_provider", "gemini")
    new_provider = st.radio(
        "Select LLM Provider",
        options=["gemini", "claude", "groq"],
        format_func=lambda x: {
            "gemini": "🟢 Gemini Flash — Free tier — Standard queries",
            "claude": "🟣 Claude Sonnet 4.6 — ~$0.01–0.02/query — Complex errors & cutover",
            "groq":   "🟠 Groq Llama 3.1 70B — Free — 14,400 req/day — Fallback",
        }[x],
        index=["gemini", "claude", "groq"].index(current),
    )

    if new_provider != current:
        if st.button(f"✅ Apply — Switch to {new_provider.capitalize()}", type="primary"):
            st.session_state.llm_provider = new_provider
            st.success(f"LLM switched to {new_provider}. All tools updated.")
            st.rerun()

    st.divider()
    st.markdown("#### Provider Comparison")
    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown("**🟢 Gemini Flash**")
        st.markdown("- ✅ Free tier\n- ✅ Native screenshot OCR\n- ✅ Fast\n- ⚠️ Daily limits apply")
    with c2:
        st.markdown("**🟣 Claude Sonnet 4.6**")
        st.markdown("- 💰 ~$0.01–0.02/query\n- ✅ Deepest reasoning\n- ✅ Best for cutover\n- ✅ Vision capable")
    with c3:
        st.markdown("**🟠 Groq Llama 3.1**")
        st.markdown("- ✅ Free — 14,400 req/day\n- ✅ Very fast\n- ❌ No vision\n- ✅ Auto-fallback")

# ── Tab 2: Clients & Projects ─────────────────────────────────────────────────
with tab2:
    st.markdown("### Session Context")
    col1, col2 = st.columns(2)
    with col1:
        session_client = st.text_input(
            "Set Active Client",
            value=st.session_state.get("active_client", ""),
        )
        if st.button("Set Client"):
            st.session_state.active_client = session_client
            st.success(f"Active client: {session_client}")
    with col2:
        session_project = st.text_input(
            "Set Active Project",
            value=st.session_state.get("active_project", ""),
        )
        if st.button("Set Project"):
            st.session_state.active_project = session_project
            st.success(f"Active project: {session_project}")

    st.divider()
    st.markdown("### Client Management")
    if not db_connected:
        st.warning("⚠️ Connect Supabase to manage clients and projects.")
    else:
        with st.form("add_client"):
            c1, c2, c3 = st.columns([2, 1, 1])
            with c1:
                new_client_name = st.text_input("Client Name", placeholder="e.g. Apple Inc")
            with c2:
                new_client_code = st.text_input("Client Code", placeholder="e.g. APPL")
            with c3:
                st.markdown("<br>", unsafe_allow_html=True)
                add_client_btn = st.form_submit_button("Add Client")
        if add_client_btn and new_client_name and new_client_code:
            try:
                db.table("clients").insert({
                    "name": new_client_name,
                    "code": new_client_code.upper(),
                }).execute()
                st.success(f"✅ Client '{new_client_name}' added.")
            except Exception as e:
                st.error(f"Error: {e}")

# ── Tab 3: Team ───────────────────────────────────────────────────────────────
with tab3:
    st.markdown("### Team Management")
    st.info("Add team members per project — used for War Room assignments and resolution attribution.")
    if not db_connected:
        st.warning("⚠️ Connect Supabase to manage team members.")
    else:
        st.markdown("*Team management UI builds in Phase 2 alongside War Room mode.*")

# ── Tab 4: Knowledge Base ─────────────────────────────────────────────────────
with tab4:
    st.markdown("### Knowledge Base Viewer")
    if not db_connected:
        st.warning("⚠️ Connect Supabase to browse the knowledge base.")
    else:
        kb_tab1, kb_tab2 = st.tabs(["Project Resolutions", "Cross-Client KB"])
        with kb_tab1:
            try:
                resolutions = db.table("error_resolutions").select("*").limit(50).execute()
                if resolutions.data:
                    import pandas as pd
                    st.dataframe(pd.DataFrame(resolutions.data), use_container_width=True)
                else:
                    st.info("No resolutions yet — start diagnosing errors in the Error Analyzer!")
            except Exception as e:
                st.error(f"Error: {e}")
        with kb_tab2:
            try:
                kb = db.table("cross_client_kb").select("*").limit(50).execute()
                if kb.data:
                    import pandas as pd
                    st.dataframe(pd.DataFrame(kb.data), use_container_width=True)
                else:
                    st.info("No cross-client entries yet — auto-populated when resolutions are saved.")
            except Exception as e:
                st.error(f"Error: {e}")

# ── Tab 5: Usage Analytics ────────────────────────────────────────────────────
with tab5:
    st.markdown("### Usage Analytics")
    if not db_connected:
        st.warning("⚠️ Connect Supabase to view usage analytics.")
    else:
        try:
            import pandas as pd
            import plotly.express as px
            logs = db.table("usage_logs").select("*").limit(200).execute()
            if logs.data:
                df_logs = pd.DataFrame(logs.data)
                col1, col2 = st.columns(2)
                with col1:
                    if "tool" in df_logs.columns:
                        fig = px.bar(
                            df_logs["tool"].value_counts().reset_index(),
                            x="tool", y="count",
                            title="Queries per Tool",
                        )
                        st.plotly_chart(fig, use_container_width=True)
                with col2:
                    if "provider" in df_logs.columns:
                        fig = px.pie(
                            df_logs["provider"].value_counts().reset_index(),
                            names="provider", values="count",
                            title="LLM Usage Split",
                        )
                        st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("No usage data yet — analytics populate as tools are used.")
        except Exception as e:
            st.error(f"Error: {e}")
