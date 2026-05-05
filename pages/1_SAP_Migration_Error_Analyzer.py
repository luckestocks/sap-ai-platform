"""
pages/1_SAP_Migration_Error_Analyzer.py
SAP Migration Co-pilot — AI error diagnostic with 4-level RAG hierarchy.
"""

import streamlit as st
from utils.llm_router import query_llm, query_llm_vision
from utils.file_loader import render_file_uploader, get_image_bytes
from utils.response_renderer import (
    render_response_card,
    render_error_type_badge,
)

st.set_page_config(
    page_title="SAP Migration Error Analyzer | SAP AI Platform",
    page_icon="🔧",
    layout="wide",
)

with open("components/styles.css") as f:
    st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)

st.markdown("# 🔧 SAP Migration Error Analyzer")
st.markdown("Diagnose SAP load errors using AI + hierarchical project memory.")

# ── Project context ───────────────────────────────────────────────────────────
with st.expander("📁 Project Context", expanded=True):
    ctx_col1, ctx_col2, ctx_col3 = st.columns(3)
    with ctx_col1:
        client = st.text_input(
            "Client",
            value=st.session_state.get("active_client", ""),
            placeholder="e.g. Apple Inc",
        )
        st.session_state.active_client = client
    with ctx_col2:
        project = st.text_input(
            "Project",
            value=st.session_state.get("active_project", ""),
            placeholder="e.g. ABC",
        )
        st.session_state.active_project = project
    with ctx_col3:
        load_phase = st.selectbox("Load Phase", ["DEV", "SIT", "UAT", "Cutover"])

st.divider()

# ── Input tabs ────────────────────────────────────────────────────────────────
input_tab1, input_tab2 = st.tabs(["📝 Paste Error Text", "📸 Upload Screenshot"])

error_text = ""
image_bytes = None
mime_type = "image/png"

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
        "🔀 LLM-only mode — skip project history, go direct to AI",
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

            # Step 3: RAG hierarchy (Phase 1 wires real DB — L4 for now)
            source_level = "l4"
            source_detail = ""
            if not llm_only:
                st.caption("📚 Knowledge base: no DB configured yet — routing to LLM (L4)")

            # Step 4: LLM diagnosis
            system_prompt = (
                "You are an expert SAP data migration consultant with deep knowledge of "
                "IDoc, BODS, LTMC, LSMW, SDI, BAPI, RFC, and SM21 error diagnosis. "
                "Always provide: (1) plain English root cause, "
                "(2) step-by-step fix with T-codes, "
                "(3) confidence level (HIGH/MEDIUM/LOW). "
                "Be specific and practical."
            )
            diagnosis_prompt = (
                f"Error Type: {error_type}\n"
                f"Load Phase: {load_phase}\n"
                f"Client: {client or 'Not specified'}\n"
                f"Project: {project or 'Not specified'}\n\n"
                f"Error:\n{error_text}\n\n"
                f"Diagnose this error. Include root cause, fix steps, T-codes, and confidence level."
            )
            response, provider = query_llm(diagnosis_prompt, system_prompt)

            # Step 5: Parse confidence
            confidence = "medium"
            resp_upper = response.upper()
            if "CONFIDENCE: HIGH" in resp_upper or "HIGH CONFIDENCE" in resp_upper:
                confidence = "high"
            elif "CONFIDENCE: LOW" in resp_upper or "LOW CONFIDENCE" in resp_upper:
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

            # Step 7: Resolution logging
            st.divider()
            st.markdown("### ✅ Log Resolution")
            st.caption("Confirm the fix applied — saves to your project knowledge base.")

            with st.form("log_resolution"):
                actual_fix = st.text_area(
                    "Actual fix applied",
                    height=100,
                    placeholder="Describe what you did to resolve this...",
                )
                time_taken = st.number_input(
                    "Time to resolve (minutes)",
                    min_value=1,
                    max_value=480,
                    value=30,
                )
                log_btn = st.form_submit_button("Save to Knowledge Base")

            if log_btn:
                if actual_fix.strip():
                    st.success(
                        "✅ Resolution saved! (DB not yet configured — "
                        "will persist to Supabase in Phase 1)"
                    )
                else:
                    st.warning("Please describe the fix before saving.")
