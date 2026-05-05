"""
pages/2_SAP_Migration_Data_Quality_Checker.py
SAP Data Quality Validator — structural + LLM business rule checks.
"""

import streamlit as st
import pandas as pd
import json
from utils.file_loader import (
    render_file_uploader,
    load_dataframe,
    render_dataframe_preview,
    dataframe_summary,
)
from utils.llm_router import query_llm

st.set_page_config(
    page_title="SAP Data Quality Checker | SAP AI Platform",
    page_icon="✅",
    layout="wide",
)

with open("components/styles.css") as f:
    st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)

st.markdown("# ✅ SAP Migration Data Quality Checker")
st.markdown("Upload any SAP data extract — get a quality score, prioritised issue list, and downloadable error report.")

st.info("🔧 **Phase 2 feature** — Skeleton ready. Full validation logic builds in Phase 2.", icon="ℹ️")

# ── Object selection ──────────────────────────────────────────────────────────
SAP_OBJECTS = [
    "Material Master (MARA/MARC/MARD)",
    "Vendor Master (LFA1/LFB1/LFM1)",
    "Customer Master (KNA1/KNB1/KNVV)",
    "Open Purchase Orders (EKKO/EKPO)",
    "Schedule Agreements (EKKO/EKPO/EKET)",
    "GL / Chart of Accounts (SKA1/SKB1)",
    "Generic — describe your object",
]

col1, col2 = st.columns([2, 1])
with col1:
    sap_object = st.selectbox("SAP Object Type", SAP_OBJECTS)
with col2:
    load_tool = st.selectbox("Load Tool", ["BODS", "LTMC / Migration Cockpit", "LSMW", "Other"])

if "Generic" in sap_object:
    st.text_input(
        "Describe your SAP object",
        placeholder="e.g. Custom Z-table for cost centre mapping",
    )

st.divider()

# ── File upload ───────────────────────────────────────────────────────────────
uploaded_file = render_file_uploader(
    label="Upload data extract (CSV or Excel)",
    accept=["csv", "xlsx", "xls"],
    key="validator_file",
    help_text="Export from BODS, LTMC, or directly from SAP using SE16/SM30.",
)

df = None
if uploaded_file:
    df, err = load_dataframe(uploaded_file)
    if err:
        st.error(f"❌ {err}")
    elif df is not None:
        render_dataframe_preview(df, max_rows=5, title="Data Preview")

validate_btn = st.button(
    "🔍 Check Data Quality",
    type="primary",
    disabled=(df is None),
)

st.divider()

# ── Validation ────────────────────────────────────────────────────────────────
if validate_btn and df is not None:

    with st.spinner("Running Layer 1 — structural checks..."):
        summary = dataframe_summary(df)
        issues = []

        for col, null_pct in summary["null_pct"].items():
            if null_pct > 50:
                issues.append({
                    "field": col,
                    "issue": f"High null rate ({null_pct}%)",
                    "severity": "Critical",
                    "affected_rows": int(summary["null_counts"][col]),
                    "fix": "Investigate source system extraction",
                })
            elif null_pct > 10:
                issues.append({
                    "field": col,
                    "issue": f"Moderate null rate ({null_pct}%)",
                    "severity": "High",
                    "affected_rows": int(summary["null_counts"][col]),
                    "fix": "Cleanse or default fill before load",
                })

        if summary["duplicate_rows"] > 0:
            issues.append({
                "field": "All columns",
                "issue": f"{summary['duplicate_rows']} fully duplicate rows detected",
                "severity": "Critical",
                "affected_rows": summary["duplicate_rows"],
                "fix": "Deduplicate before migration load",
            })

    with st.spinner("Running Layer 2 — LLM business rule checks..."):
        llm_prompt = (
            f"You are an SAP data migration expert. Analyse this data extract summary "
            f"for the SAP object: {sap_object}.\n\n"
            f"Summary:\n{json.dumps(summary, indent=2, default=str)}\n\n"
            f"Identify business rule violations, S/4HANA readiness issues, "
            f"and data quality problems. Return a JSON array of issues with fields: "
            f"field, issue, severity (Critical/High/Medium/Low), affected_rows (estimate), fix. "
            f"Return ONLY valid JSON, no markdown."
        )
        llm_response, provider = query_llm(llm_prompt)

        try:
            clean = llm_response.strip().replace("```json", "").replace("```", "")
            llm_issues = json.loads(clean)
            if isinstance(llm_issues, list):
                issues.extend(llm_issues)
        except Exception:
            st.warning("⚠️ Could not parse LLM issue list — showing structural checks only.")

    # ── Quality score ──
    critical_count = sum(1 for i in issues if i.get("severity") == "Critical")
    high_count     = sum(1 for i in issues if i.get("severity") == "High")
    total_issues   = len(issues)

    score = max(0, 100 - (critical_count * 15) - (high_count * 5) - (total_issues - critical_count - high_count) * 2)
    score_class = "quality-good" if score >= 80 else "quality-warning" if score >= 60 else "quality-poor"
    score_label = "✅ Good to Load" if score >= 80 else "⚠️ Needs Cleansing" if score >= 60 else "❌ Do Not Load"

    # ── Results ──
    st.markdown("### Quality Score")
    s1, s2, s3, s4 = st.columns(4)
    with s1:
        st.markdown(f'<div class="quality-score {score_class}">{score}%</div>', unsafe_allow_html=True)
        st.caption(score_label)
    with s2:
        st.metric("Critical Issues", critical_count)
    with s3:
        st.metric("High Issues", high_count)
    with s4:
        st.metric("Total Issues", total_issues)

    st.divider()

    if issues:
        st.markdown("### Issue Report")
        issues_df = pd.DataFrame(issues)
        st.dataframe(issues_df, use_container_width=True)

        csv_out = issues_df.to_csv(index=False)
        st.download_button(
            label="📥 Download Error Report (CSV)",
            data=csv_out,
            file_name=f"dq_report_{sap_object.split()[0].lower()}.csv",
            mime="text/csv",
        )
    else:
        st.success("🎉 No issues detected — data looks clean!")

    st.caption(f"Analysis powered by {provider}")
