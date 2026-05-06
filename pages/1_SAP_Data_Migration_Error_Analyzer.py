"""
pages/1_SAP_Migration_Error_Analyzer.py
SAP Migration Co-pilot — AI error diagnostic with 4-level RAG hierarchy.
Search order: L3 Global KB → L1 Project KB → L2 Client KB → L4 LLM
Client/project selected at save time, not search time.
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
)

st.set_page_config(
    page_title="SAP Data Migration Error Analyzer | SAP AI Platform",
    page_icon="🔧",
    layout="wide",
)

with open("components/styles.css") as f:
    st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)

st.markdown("# 🔧 SAP Data Migration Error Analyzer")
st.markdown("Diagnose SAP Data Migration load errors using AI + hierarchical project memory.")

# ── RAG level badge helper ────────────────────────────────────────────────────
def render_rag_badge(level: int):
    config = {
        1: ("🔵", "#dbeeff", "#1d6fa5", "Project KB match"),
        2: ("🟢", "#d4f5e2", "#1a7a4a", "Client KB match"),
        3: ("🟡", "#fff8d6", "#8a6d00", "Global KB match"),
        4: ("⚪", "#e8e8e8", "#555555", "LLM — no KB match found"),
    }
    icon, bg, colour, label = config[level]
    st.markdown(
        f'<span style="background:{bg};color:{colour};padding:4px 12px;'
        f'border-radius:20px;font-size:0.82rem;font-weight:600;">'
        f'{icon} {label}</span>',
        unsafe_allow_html=True,
    )


# ── Global-first RAG search ───────────────────────────────────────────────────
def global_first_rag(
    query: str,
    project_id: str = None,
    client_id: str = None,
    threshold: float = 0.70,
    match_count: int = 3,
) -> dict:
    supabase  = get_supabase()
    embedding = embed_text(query)

    # L3 first — cross-client anonymous KB
    res = supabase.rpc(
        "match_cross_client_kb",
        {
            "query_embedding": embedding,
            "match_threshold": threshold,
            "match_count": match_count,
        },
    ).execute()
    if res.data:
        return {"level": 3, "label": "Global KB", "results": res.data}

    # L1 — project-specific
    if project_id:
        res = supabase.rpc(
            "match_project_errors",
            {
                "query_embedding": embedding,
                "match_project_id": project_id,
                "match_threshold": threshold,
                "match_count": match_count,
            },
        ).execute()
        if res.data:
            return {"level": 1, "label": "Project KB", "results": res.data}

    # L2 — client-wide
    if client_id and project_id:
        res = supabase.rpc(
            "match_client_errors",
            {
                "query_embedding": embedding,
                "match_client_id": client_id,
                "exclude_project_id": project_id,
                "match_threshold": threshold,
                "match_count": match_count,
            },
        ).execute()
        if res.data:
            return {"level": 2, "label": "Client KB", "results": res.data}

    return {"level": 4, "label": "LLM Fallback", "results": []}


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
        st.success(f"✅ Will also search **{active_client_name} / {active_project_name}** KB (L1 + L2)")
    else:
        st.info("ℹ️ Global KB (L3) always searched. Select client/project to also include L1 + L2 search.")

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

    st.caption("📋 Take a snip (Win+Shift+S) then click the button below and press Ctrl+V — no saving needed.")
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
            help_text="Gemini Vision will extract the error text automatically.",
        )
        if uploaded_img:
            image_bytes, mime_type = get_image_bytes(uploaded_img)
            st.image(uploaded_img, caption="Uploaded screenshot", use_column_width=True)

# ── Options ───────────────────────────────────────────────────────────────────
opt_col1, opt_col2 = st.columns([3, 1])
with opt_col1:
    llm_only = st.checkbox(
        "🔀 LLM-only mode — skip all KB search, go direct to AI",
        value=False,
    )
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

            # Step 1: Screenshot → extract text via vision
            if image_bytes and not error_text.strip():
                vision_prompt = (
                    "You are an SAP expert. Extract the complete error message, "
                    "error codes, and any relevant log lines from this SAP screenshot. "
                    "Return only the extracted text, formatted clearly."
                )
                extracted, vis_provider = query_llm_vision(
                    prompt=vision_prompt,
                    image_bytes=image_bytes,
                    media_type=mime_type,
                )
                st.info(f"📸 Screenshot text extracted via {vis_provider}:")
                st.code(extracted)
                error_text = extracted

            # Step 2: Classify error type
            classify_prompt = (
                f"Classify this SAP error into ONE category: "
                f"IDoc | BODS | LTMC | LSMW | SDI | BAPI | RFC | SM21\n\n"
                f"Error:\n{error_text}\n\n"
                f"Return ONLY the category name, nothing else."
            )
            error_type_raw, _ = query_llm(classify_prompt)
            error_type = error_type_raw.strip().split()[0]

            st.markdown("**Detected Error Type:**")
            render_error_type_badge(error_type)
            st.markdown("")

            # Step 3: Global-first RAG search
            rag_result    = {"level": 4, "label": "LLM Fallback", "results": []}
            rag_context   = ""
            source_level  = "l4"
            source_detail = ""

            if not llm_only:
                with st.spinner("🔍 Searching knowledge base..."):
                    rag_result = global_first_rag(
                        query=error_text,
                        project_id=active_project_id,
                        client_id=active_client_id,
                    )

                level        = rag_result["level"]
                source_level = f"l{level}"

                st.markdown("**Knowledge Base:**")
                render_rag_badge(level)
                st.markdown("")

                if rag_result["results"]:
                    source_detail = f"L{level} — {rag_result['label']}"
                    rag_lines = []
                    for i, r in enumerate(rag_result["results"], 1):
                        rag_lines.append(
                            f"[Match {i} — similarity {r['similarity']:.0%}]\n"
                            f"Error: {r['error_message']}\n"
                            f"Root cause: {r['root_cause']}\n"
                            f"Fix: {r['fix_steps']}\n"
                            f"T-codes: {', '.join(r['t_codes'] or [])}"
                        )
                    rag_context = "\n\n".join(rag_lines)

                    with st.expander(
                        f"📚 {len(rag_result['results'])} similar past resolution(s) found",
                        expanded=False,
                    ):
                        for r in rag_result["results"]:
                            st.markdown(
                                f"**{r['error_code'] or 'Error'}** — "
                                f"similarity {r['similarity']:.0%} | "
                                f"phase: {r['load_phase'] or '—'}"
                            )
                            st.caption(r["fix_steps"] or "")
                            st.markdown("---")
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
                "(3) confidence level (HIGH/MEDIUM/LOW). "
                "Be specific and practical."
            )
            kb_section = (
                f"\n\nRELEVANT PAST RESOLUTIONS FROM KNOWLEDGE BASE:\n{rag_context}\n"
                f"Use these as primary reference if applicable.\n"
                if rag_context else ""
            )
            diagnosis_prompt = (
                f"Error Type: {error_type}\n"
                f"Load Phase: {load_phase}\n"
                f"Client: {active_client_name or 'Not specified'}\n"
                f"Project: {active_project_name or 'Not specified'}\n"
                f"{kb_section}\n"
                f"Error:\n{error_text}\n\n"
                f"Diagnose this error. Include root cause, fix steps, T-codes, and confidence level."
            )
            response, provider = query_llm(diagnosis_prompt, system_prompt)

            # Step 5: Parse confidence (robust — strips markdown bold before checking)
            confidence = "medium"
            resp_clean = response.upper().replace("**", "").replace("*", "")
            if any(p in resp_clean for p in [
                "CONFIDENCE: HIGH", "CONFIDENCE LEVEL: HIGH",
                "HIGH CONFIDENCE", "CONFIDENCE HIGH"
            ]):
                confidence = "high"
            elif any(p in resp_clean for p in [
                "CONFIDENCE: LOW", "CONFIDENCE LEVEL: LOW",
                "LOW CONFIDENCE", "CONFIDENCE LOW"
            ]):
                confidence = "low"

            # Step 6: Render result
            st.markdown("### Diagnosis")
            render_response_card(
                response_text=response,
                confidence=confidence,
                source_level=source_level,
                source_detail=source_detail,
                provider_used=provider,
            )

            # Persist to session for the save form below
            st.session_state["last_error_text"] = error_text
            st.session_state["last_error_type"] = error_type
            st.session_state["last_diagnosis"]  = response
            st.session_state["last_load_phase"] = load_phase


# ── Save Resolution — always visible after an analysis ───────────────────────
if st.session_state.get("last_error_text"):
    st.divider()
    st.markdown("### ✅ Save Resolution")
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
                st.selectbox(
                    "Tag to Project *",
                    options=["— select client first —"],
                    disabled=True,
                    key="save_project_disabled",
                )
                save_project_id = None

        with save_col3:
            phases     = ["DEV", "SIT", "UAT", "Cutover"]
            last_phase = st.session_state.get("last_load_phase", "DEV")
            save_phase = st.selectbox(
                "Load Phase",
                phases,
                index=phases.index(last_phase) if last_phase in phases else 0,
                key="save_phase",
            )

        actual_fix = st.text_area(
            "Actual fix applied *",
            height=100,
            placeholder="Describe exactly what you did to resolve this error...",
        )
        t_codes_input = st.text_input(
            "T-codes used (comma separated)",
            placeholder="e.g. WE20, BD54, WE19",
        )
        time_taken = st.number_input(
            "Time to resolve (minutes)", min_value=1, max_value=480, value=30
        )

        log_btn = st.form_submit_button("💾 Save to Knowledge Base", type="primary")

    if log_btn:
        if not actual_fix.strip():
            st.warning("Please describe the fix before saving.")
        elif not save_client_id:
            st.warning("Please select a client to tag this resolution.")
        elif not save_project_id:
            st.warning("Please select a project to tag this resolution.")
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
