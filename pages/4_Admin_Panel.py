"""
pages/4_Admin_Panel.py
Admin Control Panel — LLM switch, client/project management, KB viewer, analytics.
"""

import streamlit as st
from utils.supabase_client import get_supabase, check_connection, create_client_record, create_project_record

st.set_page_config(
    page_title="Admin Panel | SAP AI Platform",
    page_icon="⚙️",
    layout="wide",
)

with open("components/styles.css") as f:
    st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)

st.markdown("# ⚙️ Admin Control Panel")

conn = check_connection()
db_connected = conn["connected"]
db = get_supabase() if db_connected else None

s1, s2, s3, s4 = st.columns(4)
with s1:
    st.metric("Database", "🟢 Connected" if db_connected else "🔴 Not configured")
with s2:
    provider_map = {
        "groq":   "🟠 Groq Llama 3.3 70B",
        "claude": "🟣 Claude Sonnet 4.6",
    }
    st.metric("Active LLM", provider_map.get(st.session_state.get("llm_provider", "groq"), "Unknown"))
with s3:
    st.metric("Active Client", st.session_state.get("active_client") or "None")
with s4:
    st.metric("Resolutions", conn.get("resolution_count", 0) if db_connected else "—")

st.divider()

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

    current = st.session_state.get("llm_provider", "groq")
    new_provider = st.radio(
        "Select LLM Provider",
        options=["groq", "claude"],
        format_func=lambda x: {
            "groq":   "🟠 Groq Llama 3.3 70B — Free — 14,400 req/day — Default",
            "claude": "🟣 Claude Sonnet 4.6 — ~$0.01–0.02/query — Complex errors & cutover",
        }[x],
        index=["groq", "claude"].index(current),
    )

    if new_provider != current:
        if st.button(f"✅ Apply — Switch to {new_provider.capitalize()}", type="primary"):
            st.session_state.llm_provider = new_provider
            st.success(f"LLM switched to {new_provider}. All tools updated.")
            st.rerun()

    st.divider()
    st.markdown("#### Provider Comparison")
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**🟠 Groq Llama 3.3 70B — Default**")
        st.markdown("- ✅ Completely free\n- ✅ 14,400 req/day\n- ✅ Very fast\n- ✅ Text + Vision\n- ✅ No region restrictions")
    with c2:
        st.markdown("**🟣 Claude Sonnet 4.6 — Premium**")
        st.markdown("- 💰 ~$0.01–0.02/query\n- ✅ Deepest reasoning\n- ✅ Best for cutover\n- ✅ Text + Vision\n- ✅ Switch in one click")

# ── Tab 2: Clients & Projects ─────────────────────────────────────────────────
with tab2:
    st.markdown("### Client Management")
    if not db_connected:
        st.warning("⚠️ Connect Supabase to manage clients and projects.")
    else:
        # Add new client
        st.markdown("#### Add Client")
        with st.form("add_client"):
            c1, c2 = st.columns([3, 1])
            with c1:
                new_client_name = st.text_input("Client Name", placeholder="e.g. Apple Inc")
            with c2:
                st.markdown("<br>", unsafe_allow_html=True)
                add_client_btn = st.form_submit_button("Add Client", type="primary")
        if add_client_btn and new_client_name.strip():
            new_id = create_client_record(new_client_name.strip())
            if new_id:
                st.success(f"✅ Client '{new_client_name}' added.")
            else:
                st.error("Failed to add client.")

        st.divider()

        # Add new project
        st.markdown("#### Add Project")
        try:
            clients_data = db.table("clients").select("id, name").order("name").execute()
            clients = clients_data.data or []
            if clients:
                client_names = [c["name"] for c in clients]
                client_ids   = {c["name"]: c["id"] for c in clients}
                with st.form("add_project"):
                    p1, p2, p3 = st.columns([2, 2, 1])
                    with p1:
                        sel_client = st.selectbox("Client", options=client_names)
                    with p2:
                        new_proj_name = st.text_input("Project Name", placeholder="e.g. S4HANA Rollout Phase 1")
                    with p3:
                        st.markdown("<br>", unsafe_allow_html=True)
                        add_proj_btn = st.form_submit_button("Add Project", type="primary")
                if add_proj_btn and new_proj_name.strip():
                    new_pid = create_project_record(client_ids[sel_client], new_proj_name.strip())
                    if new_pid:
                        st.success(f"✅ Project '{new_proj_name}' added under '{sel_client}'.")
                    else:
                        st.error("Failed to add project.")
            else:
                st.info("No clients yet — add a client first.")
        except Exception as e:
            st.error(f"Error loading clients: {e}")

        st.divider()

        # View all clients and projects
        st.markdown("#### All Clients & Projects")
        try:
            clients_data = db.table("clients").select("id, name, created_at").order("name").execute()
            for client in (clients_data.data or []):
                with st.expander(f"🏢 {client['name']}"):
                    projects = db.table("projects").select("id, name, description, created_at") \
                        .eq("client_id", client["id"]).order("name").execute()
                    if projects.data:
                        for p in projects.data:
                            st.markdown(f"- **{p['name']}** — {p.get('description') or '—'}")
                    else:
                        st.caption("No projects yet.")
        except Exception as e:
            st.error(f"Error: {e}")

    st.divider()
    st.markdown("### Session Context")
    col1, col2 = st.columns(2)
    with col1:
        session_client = st.text_input(
            "Override Active Client",
            value=st.session_state.get("active_client", ""),
        )
        if st.button("Set Client"):
            st.session_state.active_client = session_client
            st.success(f"Active client: {session_client}")
    with col2:
        session_project = st.text_input(
            "Override Active Project",
            value=st.session_state.get("active_project", ""),
        )
        if st.button("Set Project"):
            st.session_state.active_project = session_project
            st.success(f"Active project: {session_project}")

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
                import pandas as pd
                resolutions = db.table("error_resolutions") \
                    .select("id, error_type, error_code, error_message, fix_steps, t_codes, load_phase, time_to_resolve, created_by, created_at") \
                    .order("created_at", desc=True).limit(100).execute()
                if resolutions.data:
                    df = pd.DataFrame(resolutions.data)
                    df["embedding"] = "…"  # hide embedding column
                    st.dataframe(df, use_container_width=True)
                    st.caption(f"{len(resolutions.data)} resolution(s) shown")
                else:
                    st.info("No resolutions yet — start diagnosing errors in the Error Analyzer!")
            except Exception as e:
                st.error(f"Error: {e}")

        with kb_tab2:
            try:
                import pandas as pd
                kb = db.table("cross_client_kb") \
                    .select("id, error_type, error_code, error_message, fix_steps, t_codes, load_phase, time_to_resolve, promoted_at") \
                    .order("promoted_at", desc=True).limit(100).execute()
                if kb.data:
                    df = pd.DataFrame(kb.data)
                    st.dataframe(df, use_container_width=True)
                    st.caption(f"{len(kb.data)} KB entries shown")
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

            # Resolution stats from error_resolutions
            res = db.table("error_resolutions") \
                .select("error_type, load_phase, time_to_resolve, created_at").execute()

            if res.data:
                df = pd.DataFrame(res.data)
                col1, col2, col3 = st.columns(3)
                col1.metric("Total Resolutions", len(df))
                col2.metric("Avg Time to Resolve", f"{df['time_to_resolve'].mean():.0f} min" if "time_to_resolve" in df else "—")
                col3.metric("Error Types", df["error_type"].nunique() if "error_type" in df else "—")

                st.divider()
                c1, c2 = st.columns(2)
                with c1:
                    if "error_type" in df.columns:
                        fig = px.bar(
                            df["error_type"].value_counts().reset_index(),
                            x="error_type", y="count",
                            title="Resolutions by Error Type",
                            labels={"error_type": "Error Type", "count": "Count"},
                        )
                        st.plotly_chart(fig, use_container_width=True)
                with c2:
                    if "load_phase" in df.columns:
                        fig = px.pie(
                            df["load_phase"].value_counts().reset_index(),
                            names="load_phase", values="count",
                            title="Resolutions by Load Phase",
                        )
                        st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("No usage data yet — analytics populate as errors are resolved and saved.")
        except Exception as e:
            st.error(f"Error: {e}")
