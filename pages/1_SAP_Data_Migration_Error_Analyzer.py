"""
pages/1_SAP_Migration_Error_Analyzer.py
SAP Migration Co-pilot — AI error diagnostic with additive multi-level KB search.
"""

import streamlit as st
from utils.llm_router import query_llm, query_llm_vision
from utils.file_loader import render_file_uploader, get_image_bytes
from utils.response_renderer import (
    render_response_card,
    render_error_type_badge,
)
from utils.supabase_client import (
    get_clients,
    get_projects,
    create_client_record,
    create_project_record,
    save_resolution,
    get_supabase,
    embed_text,
    kb_search,
)

st.set_page_config(
    page_title="SAP Migration Error Analyzer | SAP AI Platform",
    page_icon="🔧",
    layout="wide",
)

with open("components/styles.css") as f:
    st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)

st.markdown("# 🔧 SAP Data Migration Error Analyzer")
st.markdown("Diagnose SAP Data errors using AI + hierarchical project memory.")


# ── Helpers ───────────────────────────────────────────────────────────────────

def render_rag_badge(level: int, custom_label: str = None):
    config = {
        1: ("🔵", "#dbeeff", "#1d6fa5", "Project KB match"),
        2: ("🟢", "#d4f5e2", "#1a7a4a", "Client KB match"),
        3: ("🟡", "#fff8d6", "#8a6d00", "Global KB match"),
        4: ("⚪", "#e8e8e8", "#555555", "LLM — no KB match found"),
    }
    icon, bg, colour, default_label = config.get(level, config[4])
    label = custom_label or default_label
    st.markdown(
        f'<span style="background:{bg};color:{colour};padding:4px 12px;'
        f'border-radius:20px;font-size:0.82rem;font-weight:600;">'
        f'{icon} {label}</span>',
        unsafe_allow_html=True,
    )


# ── Compact KB results renderer ───────────────────────────────────────────────
# Design: each match is a single-row pill bar (metadata) + one info box (fix).
# No st.metric() — those are too tall. Everything inline via HTML.

SOURCE_PILL_STYLE = {
    "Global KB":  ("🟡", "#fff8d6", "#8a6d00"),
    "Client KB":  ("🟢", "#d4f5e2", "#1a7a4a"),
    "Project KB": ("🔵", "#dbeeff", "#1d6fa5"),
}

def _pill(label: str, value: str, bg: str = "#1e293b", fg: str = "#94a3b8") -> str:
    """Render a small metadata pill as inline HTML."""
    return (
        f'<span style="display:inline-flex;align-items:center;gap:4px;'
        f'background:{bg};color:{fg};border-radius:6px;'
        f'padding:2px 8px;font-size:0.72rem;font-weight:500;margin-right:4px;">'
        f'<span style="color:#64748b;font-size:0.68rem;">{label}</span>'
        f'<span style="color:#e2e8f0;font-weight:600;">{value}</span>'
        f'</span>'
    )

def _source_badge(kb_source: str) -> str:
    icon, bg, fg = SOURCE_PILL_STYLE.get(kb_source, ("⚪", "#e8e8e8", "#555"))
    return (
        f'<span style="background:{bg};color:{fg};border-radius:10px;'
        f'padding:2px 8px;font-size:0.70rem;font-weight:700;">'
        f'{icon} {kb_source}</span>'
    )

def render_kb_results(rag_results: list, rag_label: str):
    """Compact KB matches expander — all results, minimal vertical space per card."""
    if not rag_results:
        return

    n = len(rag_results)
    with st.expander(
        f"📚 {n} past resolution{'s' if n > 1 else ''} found — {rag_label}",
        expanded=True,
    ):
        for i, r in enumerate(rag_results, 1):
            kb_source  = r.get("kb_source", "Global KB")
            similarity = r.get("similarity", 0)
            phase      = r.get("load_phase") or "—"
            etype      = r.get("error_type") or "—"
            client     = r.get("client_name") or "—"
            project    = r.get("project_name") or "—"
            tcodes     = ", ".join(r.get("t_codes") or []) or "—"
            fix        = r.get("fix_steps") or "—"

            # ── Compact metadata row ──────────────────────────────────────────
            st.markdown(
                f'<div style="display:flex;align-items:center;flex-wrap:wrap;gap:4px;'
                f'margin-bottom:4px;margin-top:{"0" if i == 1 else "10px"};">'
                f'<span style="color:#94a3b8;font-size:0.75rem;font-weight:700;'
                f'margin-right:6px;">#{i}</span>'
                f'{_source_badge(kb_source)}'
                f'{_pill("match", f"{similarity:.0%}", bg="#1a2e1a", fg="#4ade80")}'
                f'{_pill("phase", phase)}'
                f'{_pill("type", etype)}'
                f'{_pill("client", client)}'
                f'{_pill("project", project)}'
                f'{_pill("t-codes", tcodes)}'
                f'</div>',
                unsafe_allow_html=True,
            )

            # ── Fix applied — compact info box ────────────────────────────────
            st.markdown(
                f'<div style="background:#0f172a;border-left:3px solid #334155;'
                f'border-radius:0 6px 6px 0;padding:6px 10px;'
                f'font-size:0.80rem;color:#cbd5e1;line-height:1.5;'
                f'margin-bottom:2px;">'
                f'<span style="color:#64748b;font-size:0.68rem;font-weight:600;'
                f'text-transform:uppercase;letter-spacing:0.04em;">Fix applied · </span>'
                f'{fix}'
                f'</div>',
                unsafe_allow_html=True,
            )

            if i < n:
                st.markdown(
                    '<hr style="border:none;border-top:1px solid #1e293b;margin:6px 0;">',
                    unsafe_allow_html=True,
                )


# ── Optional context ──────────────────────────────────────────────────────────
with st.expander("📁 Project Context (optional — refines KB search, or set when saving)", expanded=False):
    ctx_col1, ctx_col2, ctx_col3 = st.columns(3)

    with ctx_col1:
        clients      = get_clients()
        client_names = [c["name"] for c in clients]
        client_ids   = {c["name"]: c["id"] for c in clients}

        selected_client = st.selectbox(
            "Client",
            options=["— none —"] + client_names + ["➕ New client…"],
            index=0,
            key="ctx_client",
        )
        if selected_client == "➕ New client…":
            new_client_name = st.text_input("New client name", key="new_client_name")
            if st.button("Create client") and new_client_name.strip():
                new_id = create_client_record(new_client_name.strip())
                if new_id:
                    st.success(f"Client '{new_client_name}' created!")
                    st.rerun()
            active_client_id   = None
            active_client_name = None
        elif selected_client == "— none —":
            active_client_id   = None
            active_client_name = None
        else:
            active_client_id   = client_ids[selected_client]
            active_client_name = selected_client
            st.session_state.active_client = active_client_name

    with ctx_col2:
        active_project_id   = None
        active_project_name = None

        if active_client_id:
            projects      = get_projects(active_client_id)
            project_names = [p["name"] for p in projects]
            project_ids   = {p["name"]: p["id"] for p in projects}

            selected_project = st.selectbox(
                "Project",
                options=["— none —"] + project_names + ["➕ New project…"],
                index=0,
                key="ctx_project",
            )
            if selected_project == "➕ New project…":
                new_proj_name = st.text_input("New project name", key="new_proj_name")
                new_proj_desc = st.text_input("Description (optional)", key="new_proj_desc")
                if st.button("Create project") and new_proj_name.strip():
                    new_pid = create_project_record(
                        active_client_id, new_proj_name.strip(), new_proj_desc.strip()
                    )
                    if new_pid:
                        st.success(f"Project '{new_proj_name}' created!")
                        st.rerun()
            elif selected_project != "— none —":
                active_project_id   = project_ids[selected_project]
                active_project_name = selected_project
                st.session_state.active_project = active_project_name
        else:
            st.selectbox("Project", options=["— select a client first —"], disabled=True)

    with ctx_col3:
        load_phase = st.selectbox("Load Phase", ["DEV", "SIT", "UAT", "Cutover"])

    if active_client_id and active_project_id:
        st.success(
            f"✅ Searching **L1 Project + L2 Client + L3 Global KB** "
            f"— {active_client_name} / {active_project_name}"
        )
    elif active_client_id:
        st.info(f"ℹ️ Searching **L2 Client + L3 Global KB** — {active_client_name}")
    else:
        st.info("ℹ️ Searching **L3 Global KB** — all clients and projects.")

st.divider()

# ── Input tabs ────────────────────────────────────────────────────────────────
input_tab1, input_tab2 = st.tabs(["📝 Paste Error Text", "📸 Upload Screenshot"])

error_text  = ""
image_bytes = None
mime_type   = "image/png"

with input_tab1:
    error_text = st.text_area(
        "Paste SAP error message, status code, or log snippet",
        height=180,
        placeholder=(
            "E.g.:\n"
            "E0001 Partner profile not found for 1000/LS\n"
            "WE02: IDoc status 51 — Error in ALE layer\n"
            "BODS job failed: DataStore connection timeout"
        ),
    )

with input_tab2:
    from streamlit_paste_button import paste_image_button as pbutton
    import io

    st.caption("📋 Take a snip (Win+Shift+S) then click the button below and press Ctrl+V.")
    paste_result = pbutton(
        label="📋 Paste Screenshot",
        background_color="#1E88E5",
        hover_background_color="#1565C0",
        key="paste_screenshot",
    )

    if paste_result.image_data is not None:
        img = paste_result.image_data
        st.image(img, caption="Pasted screenshot", use_column_width=True)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        image_bytes = buf.getvalue()
        mime_type   = "image/png"
    else:
        st.markdown("— or upload a file —")
        uploaded_img = render_file_uploader(
            label="Upload error screenshot (PNG, JPG, WEBP)",
            accept=["png", "jpg", "jpeg", "webp"],
            key="copilot_screenshot",
            help_text="Vision LLM will extract the error text automatically.",
        )
        if uploaded_img:
            image_bytes, mime_type = get_image_bytes(uploaded_img)
            st.image(uploaded_img, caption="Uploaded screenshot", use_column_width=True)


# ── Groq usage tracker ────────────────────────────────────────────────────────
from datetime import datetime, timezone

today_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d")
if st.session_state.get("groq_date") != today_utc:
    st.session_state["groq_date"]  = today_utc
    st.session_state["groq_calls"] = 0

groq_calls     = st.session_state.get("groq_calls", 0)
groq_analyses  = groq_calls // 2
groq_remaining = max(0, 500 - groq_analyses)
reset_ist      = "5:30 AM IST"

groq_colour = "#2ecc71" if groq_remaining > 200 else "#f39c12" if groq_remaining > 50 else "#e74c3c"

if st.session_state.get("llm_provider", "groq") == "groq":
    st.markdown(
        f'<div style="background:#1a1a2e;border:1px solid {groq_colour};border-radius:8px;'
        f'padding:8px 16px;margin-bottom:8px;display:flex;justify-content:space-between;align-items:center;">'
        f'<span style="color:{groq_colour};font-size:0.85rem;font-weight:600;">'
        f'⚡ Groq today: {groq_analyses} used &nbsp;|&nbsp; ~{groq_remaining} remaining</span>'
        f'<span style="color:#888;font-size:0.78rem;">Resets {reset_ist} · 1,000 req/day</span>'
        f'</div>',
        unsafe_allow_html=True,
    )
    if groq_remaining == 0:
        st.error("🚫 Daily Groq limit reached. Switch to Claude in Admin Panel or wait until 5:30 AM IST.")
    elif groq_remaining <= 50:
        st.warning(f"⚠️ Only ~{groq_remaining} analyses left today. Consider switching to Claude.")


# ── Options ───────────────────────────────────────────────────────────────────
opt_col1, opt_col2 = st.columns([3, 1])
with opt_col1:
    llm_only = st.checkbox("🔀 LLM-only mode — skip KB search, go direct to AI", value=False)
with opt_col2:
    diagnose_btn = st.button("⚡ Analyze Error", type="primary", use_container_width=True)

st.divider()


# ── Diagnosis ─────────────────────────────────────────────────────────────────
if diagnose_btn:
    has_input = bool(error_text.strip()) or image_bytes is not None

    if not has_input:
        st.warning("Please paste an error message or upload a screenshot.")
    else:
        with st.spinner("Analysing error..."):

            # Step 1: Screenshot → text
            if image_bytes and not error_text.strip():
                vision_prompt = (
                    "You are an SAP expert. Extract the complete error message, "
                    "error codes, and any relevant log lines from this SAP screenshot. "
                    "Return only the extracted text, formatted clearly."
                )
                extracted, vis_provider = query_llm_vision(
                    prompt=vision_prompt, image_bytes=image_bytes, media_type=mime_type,
                )
                st.info(f"📸 Screenshot text extracted via {vis_provider}:")
                st.code(extracted)
                error_text = extracted

            # Step 2: Classify error type
            classify_prompt = (
                f"Classify this SAP error into ONE category: "
                f"IDoc | BODS | LTMC | LSMW | SDI | BAPI | RFC | SM21\n\n"
                f"Error:\n{error_text}\n\nReturn ONLY the category name, nothing else."
            )
            error_type_raw, _ = query_llm(classify_prompt)
            st.session_state["groq_calls"] = st.session_state.get("groq_calls", 0) + 1
            error_type = error_type_raw.strip().split()[0]

            st.markdown("**Detected Error Type:**")
            render_error_type_badge(error_type)
            st.markdown("")

            # Step 3: Additive KB search
            rag_result  = {"level": 4, "label": "LLM Fallback", "results": [], "summary_label": "LLM Fallback"}
            rag_context = ""
            source_level  = "l4"
            source_detail = ""

            if not llm_only:
                with st.spinner("🔍 Searching knowledge base..."):
                    rag_result = kb_search(
                        query=error_text,
                        project_id=active_project_id,
                        client_id=active_client_id,
                    )

                results       = rag_result.get("results", [])
                summary_label = rag_result.get("summary_label", "Global KB")
                source_level  = f"l{rag_result.get('level', 4)}"

                st.markdown("**Knowledge Base:**")
                if results:
                    render_rag_badge(3, custom_label=summary_label)
                    source_detail = summary_label
                else:
                    render_rag_badge(4)
                st.markdown("")

                if results:
                    rag_lines = []
                    for i, r in enumerate(results, 1):
                        rag_lines.append(
                            f"[Match {i} — {r.get('kb_source','KB')} — {r['similarity']:.0%}]\n"
                            f"Error: {r['error_message']}\n"
                            f"Fix: {r['fix_steps']}\n"
                            f"T-codes: {', '.join(r.get('t_codes') or [])}"
                        )
                    rag_context = "\n\n".join(rag_lines)
                    render_kb_results(results, summary_label)

            else:
                st.caption("🔀 LLM-only mode — KB search skipped")
                render_rag_badge(4)
                st.markdown("")

            # Step 4: LLM diagnosis
            system_prompt = (
                "You are an expert SAP data migration consultant with deep knowledge of "
                "IDoc, BODS, LTMC, LSMW, SDI, BAPI, RFC, and SM21 error diagnosis. "
                "Always provide: (1) plain English root cause, "
                "(2) step-by-step fix with T-codes, "
                "(3) confidence level (HIGH/MEDIUM/LOW). Be specific and practical."
            )
            kb_section = (
                f"\n\nRELEVANT PAST RESOLUTIONS FROM KNOWLEDGE BASE:\n{rag_context}\n"
                f"Multiple resolutions may exist — consider all of them.\n"
                if rag_context else ""
            )
            diagnosis_prompt = (
                f"Error Type: {error_type}\nLoad Phase: {load_phase}\n"
                f"Client: {active_client_name or 'Not specified'}\n"
                f"Project: {active_project_name or 'Not specified'}\n"
                f"{kb_section}\nError:\n{error_text}\n\n"
                f"Diagnose this error. Include root cause, fix steps, T-codes, and confidence level."
            )
            response, provider = query_llm(diagnosis_prompt, system_prompt)
            if provider == "groq":
                st.session_state["groq_calls"] = st.session_state.get("groq_calls", 0) + 1

            # Step 5: Parse confidence
            confidence = "medium"
            resp_clean = response.upper().replace("**", "").replace("*", "")
            if any(p in resp_clean for p in ["CONFIDENCE: HIGH", "CONFIDENCE LEVEL: HIGH", "HIGH CONFIDENCE", "CONFIDENCE HIGH"]):
                confidence = "high"
            elif any(p in resp_clean for p in ["CONFIDENCE: LOW", "CONFIDENCE LEVEL: LOW", "LOW CONFIDENCE", "CONFIDENCE LOW"]):
                confidence = "low"

            # Step 6: Persist to session
            st.session_state.update({
                "last_error_text":    error_text,
                "last_error_type":    error_type,
                "last_diagnosis":     response,
                "last_load_phase":    load_phase,
                "last_confidence":    confidence,
                "last_source_level":  source_level,
                "last_source_detail": source_detail,
                "last_provider":      provider,
                "last_rag_results":   rag_result.get("results", []),
                "last_rag_level":     rag_result.get("level", 4),
                "last_rag_label":     rag_result.get("summary_label", "LLM Fallback"),
                "chat_history":       [],
            })
            st.rerun()


# ── Persistent Diagnosis ──────────────────────────────────────────────────────
if st.session_state.get("last_diagnosis"):

    if st.session_state.get("last_error_type"):
        st.markdown("**Detected Error Type:**")
        render_error_type_badge(st.session_state["last_error_type"])
        st.markdown("")

    rag_results = st.session_state.get("last_rag_results", [])
    rag_label   = st.session_state.get("last_rag_label", "LLM Fallback")

    st.markdown("**Knowledge Base:**")
    if rag_results:
        render_rag_badge(3, custom_label=rag_label)
    else:
        render_rag_badge(4)
    st.markdown("")

    render_kb_results(rag_results, rag_label)

    st.markdown("### Diagnosis")
    render_response_card(
        response_text=st.session_state["last_diagnosis"],
        confidence=st.session_state.get("last_confidence", "medium"),
        source_level=st.session_state.get("last_source_level", "l4"),
        source_detail=st.session_state.get("last_source_detail", ""),
        provider_used=st.session_state.get("last_provider", ""),
    )


# ── Follow-up Chat ────────────────────────────────────────────────────────────
if st.session_state.get("last_diagnosis"):
    st.divider()
    st.markdown("### 💬 Follow-up Questions")
    st.caption("Ask anything based on the diagnosis above.")

    if "chat_history" not in st.session_state:
        st.session_state["chat_history"] = []

    for msg in st.session_state["chat_history"]:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    followup = st.chat_input("Ask a follow-up question about this error...")

    if followup:
        st.session_state["chat_history"].append({"role": "user", "content": followup})
        with st.chat_message("user"):
            st.markdown(followup)

        history_text = "\n".join(
            f"{'User' if m['role'] == 'user' else 'Assistant'}: {m['content']}"
            for m in st.session_state["chat_history"][:-1]
        )

        followup_system = (
            "You are an expert SAP data migration consultant. "
            "Answer the follow-up concisely and practically, referencing the original diagnosis. "
            "Include T-codes and specific steps where applicable."
        )
        followup_prompt = (
            f"ORIGINAL ERROR:\n{st.session_state['last_error_text']}\n\n"
            f"YOUR PREVIOUS DIAGNOSIS:\n{st.session_state['last_diagnosis']}\n\n"
            + (f"CONVERSATION SO FAR:\n{history_text}\n\n" if history_text else "")
            + f"USER FOLLOW-UP:\n{followup}"
        )

        with st.chat_message("assistant"):
            with st.spinner("Thinking..."):
                followup_response, _ = query_llm(followup_prompt, followup_system)
            st.markdown(followup_response)

        st.session_state["chat_history"].append({"role": "assistant", "content": followup_response})


# ── Save Resolution ───────────────────────────────────────────────────────────
if st.session_state.get("last_error_text"):
    st.divider()
    with st.expander("✅ Save Resolution", expanded=False):
        st.caption("Tag this resolution to a client & project, then save it to the knowledge base.")

        with st.form("log_resolution"):
            save_col1, save_col2, save_col3 = st.columns(3)

            with save_col1:
                save_clients      = get_clients()
                save_client_names = [c["name"] for c in save_clients]
                save_client_ids   = {c["name"]: c["id"] for c in save_clients}
                save_client_sel   = st.selectbox(
                    "Tag to Client *",
                    options=["— select —"] + save_client_names,
                    key="save_client",
                )
                save_client_id = save_client_ids.get(save_client_sel)

            with save_col2:
                if save_client_id:
                    save_projects      = get_projects(save_client_id)
                    save_project_names = [p["name"] for p in save_projects]
                    save_project_ids   = {p["name"]: p["id"] for p in save_projects}
                    save_project_sel   = st.selectbox(
                        "Tag to Project *",
                        options=["— select —"] + save_project_names,
                        key="save_project",
                    )
                    save_project_id = save_project_ids.get(save_project_sel)
                else:
                    st.selectbox("Tag to Project *", options=["— select client first —"],
                                 disabled=True, key="save_project_disabled")
                    save_project_id = None

            with save_col3:
                phases     = ["DEV", "SIT", "UAT", "Cutover"]
                last_phase = st.session_state.get("last_load_phase", "DEV")
                save_phase = st.selectbox(
                    "Load Phase", phases,
                    index=phases.index(last_phase) if last_phase in phases else 0,
                    key="save_phase",
                )

            actual_fix    = st.text_area("Actual fix applied *", height=100,
                                         placeholder="Describe exactly what you did to resolve this error...")
            t_codes_input = st.text_input("T-codes used (comma separated)", placeholder="e.g. WE20, BD54, WE19")
            time_taken    = st.number_input("Time to resolve (minutes)", min_value=1, max_value=480, value=30)

            log_btn = st.form_submit_button("💾 Save to Knowledge Base", type="primary")

    if log_btn:
        if not actual_fix.strip():
            st.warning("Please describe the fix before saving.")
        elif not save_client_id:
            st.warning("Please select a client.")
        elif not save_project_id:
            st.warning("Please select a project.")
        else:
            t_codes = [t.strip().upper() for t in t_codes_input.split(",") if t.strip()]
            with st.spinner("Saving to knowledge base..."):
                result = save_resolution(
                    client_id=save_client_id,
                    project_id=save_project_id,
                    error_message=st.session_state["last_error_text"],
                    root_cause=st.session_state["last_diagnosis"],
                    fix_steps=actual_fix,
                    error_type=st.session_state.get("last_error_type", ""),
                    t_codes=t_codes,
                    load_phase=save_phase,
                    time_to_resolve=int(time_taken),
                    created_by="Sparky",
                )
            if result["status"] == "saved":
                st.success(
                    f"✅ Saved to Project KB (L1) and promoted to Global KB (L3)!\n\n"
                    f"Resolution ID: `{result['resolution_id']}`"
                )
                st.session_state.pop("last_error_text", None)
            else:
                st.error("❌ Failed to save. Check Supabase connection.")
