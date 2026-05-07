"""
pages/5_Legacy_SAP_Mapper.py
Legacy ERP → SAP Field Mapper
AI-powered field mapping with review interface and Excel export.
"""

import streamlit as st
import pandas as pd
import json
import io
from utils.llm_router import query_llm
from utils.file_loader import render_file_uploader

st.set_page_config(
    page_title="Legacy SAP Mapper | SAP AI Platform",
    page_icon="🗺️",
    layout="wide",
)

with open("components/styles.css") as f:
    st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)

st.markdown("# 🗺️ Legacy ERP → SAP Field Mapper")
st.markdown("Upload your legacy system extract and data dictionary — AI maps fields to SAP tables and you review.")

st.divider()

# ── SAP module knowledge embedded ────────────────────────────────────────────
SAP_KNOWLEDGE = """
Key SAP tables by module:

MM (Materials Management):
- MARA: General Material Data (MATNR, MTART, MBRSH, MEINS, MATKL, BRGEW, NTGEW, GEWEI, VOLUM, VOLEH, BISMT)
- MARC: Plant Data for Material (MATNR, WERKS, PSTAT, MMSTA, BESKZ, SOBSL, MINBE, EISBE, MABST)
- MARD: Storage Location Data (MATNR, WERKS, LGORT, LABST, UMLME, INSME, EINME, AUSME)
- MARM: Units of Measure (MATNR, MEINH, UMREZ, UMREN, BRGEW, NTGEW, VOLUM, EAN11)
- MAKT: Material Descriptions (MATNR, SPRAS, MAKTX)
- MVKE: Sales Data for Material (MATNR, VKORG, VTWEG, VERSG, AUMNG, AUPOS, AUPLF, KAUTB)
- EINA: Purchasing Info Record General (INFNR, MATNR, LIFNR, WERKS, UEBTO, UEBTK, UNTTO)

SD (Sales & Distribution):
- KNA1: General Customer Data (KUNNR, LAND1, NAME1, NAME2, ORT01, PSTLZ, REGIO, STRAS, TELF1, STCEG, KTOKD)
- KNB1: Customer Company Code Data (KUNNR, BUKRS, AKONT, ZTERM, ZWELS, ZAHLS, KVERM)
- KNVV: Customer Sales Data (KUNNR, VKORG, VTWEG, SPART, BZIRK, VKBUR, VKGRP, WAERS, KALKS, KONDA)
- KNVP: Customer Partner Functions (KUNNR, VKORG, VTWEG, SPART, PARVW, KUNN2, DEFPA)
- VBAK: Sales Order Header (VBELN, ERDAT, AUART, VKORG, VTWEG, SPART, KUNNR)

FI (Finance):
- LFA1: Vendor General Data (LIFNR, LAND1, NAME1, NAME2, ORT01, PSTLZ, REGIO, STRAS, TELF1, STCEG, KTOKK)
- LFB1: Vendor Company Code Data (LIFNR, BUKRS, AKONT, ZTERM, ZWELS, ZAHLS, MINDK)
- LFM1: Vendor Purchasing Organisation Data (LIFNR, EKORG, WAERS, ZTERM, INCO1, INCO2)
- SKA1: GL Account Master Chart of Accounts (SAKNR, KTOPL, KTOKS, XBILK, GVTYP, MWSKZ)
- SKB1: GL Account Master Company Code (SAKNR, BUKRS, WAERS, XOPVW, XKRES, XZPFK)
- BKPF: Accounting Document Header (BUKRS, BELNR, GJAHR, BLDAT, BUDAT, BLART, WAERS)
- BSEG: Accounting Document Segment (BUKRS, BELNR, GJAHR, BUZEI, KOART, KUNNR, LIFNR, SAKNR, DMBTR, WRBTR)

WM (Warehouse Management):
- LGPLA: Storage Bins (LGNUM, LGPLA, LGTYP, LPTYP, LGBER, SKZUB, SKZUE, SKZUA, SKZUS)
- LTBK: Transfer Order Header (TANUM, LGNUM, TANUM, TBNUM, TRART, LGTYP, LGPLA)
- LQUA: Quants (LGNUM, LGTYP, LGPLA, LQNUM, MATNR, WERKS, LGORT, CHARG, BESTQ, VERME)

PP (Production Planning):
- CRHD: Work Center Header (OBJID, WERKS, ARBPL, VERWE, BEGDA, ENDDA, KTSCH, LOEVM)
- CRCA: Work Center Capacity (OBJID, KAPID, WERKS, BEGDA, ENDDA, KAPAZ, KAPTY)
- PLKO: Routing Header (PLNTY, PLNNR, PLNKN, WERKS, STATU, ANWDT, LOEKZ)
- PLPO: Routing Operations (PLNTY, PLNNR, PLNKN, PLNAL, VORNR, ARBPL, WERKS, LTXA1, ARBID)

HR (Human Resources):
- PA0001: Organisational Assignment (PERNR, BEGDA, ENDDA, BUKRS, WERKS, BTRTL, ABKRS, KOSTL, STELL)
- PA0002: Personal Data (PERNR, BEGDA, ENDDA, VORNA, NACHN, GBDAT, GESCH, NATIO, SPRSL)
- PA0007: Planned Working Time (PERNR, BEGDA, ENDDA, SCHKZ, EMPCT, ZTERF)
- PA0008: Basic Pay (PERNR, BEGDA, ENDDA, TRFGR, TRFST, BSGRD, LGA01, BET01)

Common transformation patterns:
- Date formats: YYYYMMDD ↔ DD/MM/YYYY ↔ MM/DD/YYYY ↔ YYYY-MM-DD
- Boolean: Y/N ↔ X/blank ↔ 1/0 ↔ true/false
- Name splits: Full Name → VORNA (first) + NACHN (last)
- Address splits: Full Address → STRAS + ORT01 + PSTLZ + REGIO + LAND1
- UoM conversion: EA→ST, PCS→ST, LB→LB, KGS→KG
- Currency: 3-char ISO code usually same, but local codes may differ
- Status codes: Active/Inactive → X/blank or 1/0
"""

# ── Helper functions ──────────────────────────────────────────────────────────

def detect_legacy_system(df_extract, df_dict):
    """Ask LLM to detect the legacy ERP system from the data."""
    sample = df_extract.head(5).to_string() if df_extract is not None else "Not provided"
    fields = df_dict.to_string() if df_dict is not None else "Not provided"

    prompt = f"""You are an expert SAP data migration consultant.
Analyse these legacy system artifacts and identify the source ERP system.

DATA SAMPLE (first 5 rows):
{sample}

DATA DICTIONARY / FIELD LIST:
{fields}

Based on field naming conventions, table names, data patterns, and any system-specific identifiers,
identify the legacy ERP system. Common systems: MTD (Mapics/To-Increase), QAD, Oracle EBS, Infor,
JD Edwards, Sage, Microsoft Dynamics, SAP legacy, custom/bespoke.

Respond ONLY with valid JSON — no markdown, no explanation:
{{
  "system": "system name",
  "confidence": "HIGH|MEDIUM|LOW",
  "reasoning": "one sentence explanation",
  "module_guess": "what business module this data likely covers e.g. Customer Master, Vendor Master, Material Master, GL Accounts, Inventory, HR etc"
}}"""

    response, _ = query_llm(prompt)
    try:
        clean = response.strip().replace("```json", "").replace("```", "").strip()
        return json.loads(clean)
    except Exception:
        return {"system": "Unknown", "confidence": "LOW", "reasoning": "Could not parse response", "module_guess": "Unknown"}


def generate_mappings(df_extract, df_dict, legacy_system, sap_module_hint):
    """Generate field-level mappings from legacy to SAP."""
    sample = df_extract.head(10).to_string() if df_extract is not None else "Not provided"
    fields = df_dict.to_string() if df_dict is not None else "Not provided"

    prompt = f"""You are an expert SAP data migration consultant with deep knowledge of SAP data structures.

LEGACY SYSTEM: {legacy_system}
SAP MODULE CONTEXT: {sap_module_hint}

LEGACY DATA SAMPLE:
{sample}

LEGACY DATA DICTIONARY:
{fields}

SAP TABLE REFERENCE:
{SAP_KNOWLEDGE}

Analyse every legacy field and generate a field mapping to SAP.
For each legacy field produce:
- legacy_field: exact field name from the input
- legacy_description: description from data dictionary (or infer from name/data)
- legacy_type: data type (string, integer, date, boolean, decimal)
- sap_object: business object name (e.g. Customer Master, Material Master, Vendor Master, GL Account)
- sap_table: SAP table name (e.g. KNA1, MARA, LFA1)
- sap_field: SAP field name (e.g. KUNNR, MATNR, LIFNR)
- sap_description: SAP field description
- confidence: HIGH (obvious match) | MEDIUM (likely match) | LOW (unsure)
- transformation: transformation rule needed, e.g. "Direct copy", "Date format DDMMYYYY → YYYYMMDD", "Y/N → X/blank", "Split: first word only", "Lookup required", "No SAP equivalent"
- notes: any important migration notes or warnings

Rules:
- If a field has NO SAP equivalent, set sap_table and sap_field to "NO_MATCH" and confidence to "LOW"
- Group related fields to the same sap_object
- Be specific about transformation rules

Respond ONLY with a valid JSON array — no markdown backticks, no explanation:
[
  {{
    "legacy_field": "...",
    "legacy_description": "...",
    "legacy_type": "...",
    "sap_object": "...",
    "sap_table": "...",
    "sap_field": "...",
    "sap_description": "...",
    "confidence": "...",
    "transformation": "...",
    "notes": "..."
  }}
]"""

    response, _ = query_llm(prompt, max_tokens=4000)
    try:
        clean = response.strip().replace("```json", "").replace("```", "").strip()
        # Find the JSON array
        start = clean.find("[")
        end   = clean.rfind("]") + 1
        if start >= 0 and end > start:
            return json.loads(clean[start:end])
        return []
    except Exception as e:
        st.error(f"Failed to parse mapping response: {e}")
        return []


def confidence_badge(conf):
    colours = {
        "HIGH":   ("#d4f5e2", "#1a7a4a"),
        "MEDIUM": ("#fff8d6", "#8a6d00"),
        "LOW":    ("#fde8e8", "#c0392b"),
    }
    bg, fg = colours.get(conf, ("#e8e8e8", "#555"))
    return f'<span style="background:{bg};color:{fg};padding:2px 10px;border-radius:12px;font-size:0.78rem;font-weight:600;">{conf}</span>'


def status_badge(status):
    colours = {
        "✅ Accepted": ("#d4f5e2", "#1a7a4a"),
        "⏳ Pending":  ("#fff8d6", "#8a6d00"),
        "❌ Rejected": ("#fde8e8", "#c0392b"),
    }
    bg, fg = colours.get(status, ("#e8e8e8", "#555"))
    return f'<span style="background:{bg};color:{fg};padding:2px 10px;border-radius:12px;font-size:0.78rem;font-weight:600;">{status}</span>'


# ── Step 1: Upload ────────────────────────────────────────────────────────────
st.markdown("## Step 1 — Upload Legacy System Files")
col1, col2 = st.columns(2)

with col1:
    st.markdown("**📊 Data Extract** — sample rows from the legacy table")
    extract_file = render_file_uploader(
        label="Upload CSV or Excel extract",
        accept=["csv", "xlsx", "xls"],
        key="mapper_extract",
        help_text="Upload a sample of actual legacy data (up to 500 rows used for analysis).",
    )

with col2:
    st.markdown("**📋 Data Dictionary** — field names, types, descriptions")
    dict_file = render_file_uploader(
        label="Upload CSV or Excel data dictionary",
        accept=["csv", "xlsx", "xls"],
        key="mapper_dict",
        help_text="Upload your field specification document. Columns: field name, data type, description.",
    )

# Load files
df_extract = None
df_dict    = None

if extract_file:
    try:
        if extract_file.name.endswith(".csv"):
            df_extract = pd.read_csv(extract_file).head(500)
        else:
            df_extract = pd.read_excel(extract_file).head(500)
        st.success(f"✅ Extract loaded — {len(df_extract)} rows, {len(df_extract.columns)} fields")
        with st.expander("Preview extract", expanded=False):
            st.dataframe(df_extract.head(5), use_container_width=True)
    except Exception as e:
        st.error(f"Failed to load extract: {e}")

if dict_file:
    try:
        if dict_file.name.endswith(".csv"):
            df_dict = pd.read_csv(dict_file)
        else:
            df_dict = pd.read_excel(dict_file)
        st.success(f"✅ Data dictionary loaded — {len(df_dict)} fields defined")
        with st.expander("Preview data dictionary", expanded=False):
            st.dataframe(df_dict.head(10), use_container_width=True)
    except Exception as e:
        st.error(f"Failed to load dictionary: {e}")

# ── Step 2: ERP Detection ─────────────────────────────────────────────────────
if df_extract is not None or df_dict is not None:
    st.divider()
    st.markdown("## Step 2 — Legacy System Detection")

    if st.button("🔍 Detect Legacy ERP System", type="primary"):
        with st.spinner("Analysing your files to identify the legacy ERP..."):
            detection = detect_legacy_system(df_extract, df_dict)
            st.session_state["mapper_detection"] = detection
            st.session_state["mapper_confirmed"]  = False
            st.session_state["mapper_mappings"]   = None
            st.session_state["mapper_review"]     = None

    if st.session_state.get("mapper_detection"):
        det = st.session_state["mapper_detection"]
        conf_col, info_col = st.columns([1, 3])

        with conf_col:
            st.markdown(
                f'<div style="background:#1a1a2e;border:2px solid #1E88E5;border-radius:12px;'
                f'padding:20px;text-align:center;">'
                f'<div style="font-size:2rem;">🖥️</div>'
                f'<div style="font-size:1.4rem;font-weight:700;color:#fff;margin:8px 0;">{det["system"]}</div>'
                f'{confidence_badge(det["confidence"])}'
                f'</div>',
                unsafe_allow_html=True,
            )
        with info_col:
            st.markdown(f"**Reasoning:** {det['reasoning']}")
            st.markdown(f"**Detected module:** {det['module_guess']}")
            st.markdown("")

            if not st.session_state.get("mapper_confirmed"):
                confirm_col1, confirm_col2 = st.columns(2)
                with confirm_col1:
                    if st.button("✅ Yes, this is correct", type="primary"):
                        st.session_state["mapper_confirmed"]    = True
                        st.session_state["mapper_system_final"] = det["system"]
                        st.session_state["mapper_module_final"] = det["module_guess"]
                        st.rerun()
                with confirm_col2:
                    if st.button("✏️ No, let me specify"):
                        st.session_state["mapper_override"] = True
                        st.rerun()

            if st.session_state.get("mapper_override") and not st.session_state.get("mapper_confirmed"):
                with st.form("override_system"):
                    ov1, ov2 = st.columns(2)
                    with ov1:
                        manual_system = st.text_input("Legacy ERP name", placeholder="e.g. QAD, Oracle EBS, Infor")
                    with ov2:
                        manual_module = st.text_input("Module / object type", placeholder="e.g. Customer Master, Material Master")
                    if st.form_submit_button("Confirm", type="primary"):
                        st.session_state["mapper_confirmed"]    = True
                        st.session_state["mapper_system_final"] = manual_system
                        st.session_state["mapper_module_final"] = manual_module
                        st.rerun()

            if st.session_state.get("mapper_confirmed"):
                st.success(f"✅ Confirmed — **{st.session_state['mapper_system_final']}** | {st.session_state['mapper_module_final']}")

# ── Step 3: Generate Mappings ─────────────────────────────────────────────────
if st.session_state.get("mapper_confirmed"):
    st.divider()
    st.markdown("## Step 3 — Generate SAP Field Mappings")

    if st.button("⚡ Generate Mappings", type="primary"):
        with st.spinner("AI is mapping legacy fields to SAP tables... this may take 20–30 seconds."):
            mappings = generate_mappings(
                df_extract,
                df_dict,
                st.session_state["mapper_system_final"],
                st.session_state["mapper_module_final"],
            )
            if mappings:
                # Add review status and notes to each mapping
                for m in mappings:
                    m["status"] = "⏳ Pending"
                    m["reviewer_notes"] = ""
                st.session_state["mapper_mappings"] = mappings
                st.session_state["mapper_review"]   = {i: m.copy() for i, m in enumerate(mappings)}
                st.success(f"✅ {len(mappings)} field mappings generated. Review below.")
                st.rerun()
            else:
                st.error("No mappings generated. Try again or check your input files.")

# ── Step 4: Review Interface ──────────────────────────────────────────────────
if st.session_state.get("mapper_review"):
    st.divider()
    st.markdown("## Step 4 — Review & Confirm Mappings")

    review = st.session_state["mapper_review"]
    total     = len(review)
    accepted  = sum(1 for m in review.values() if m["status"] == "✅ Accepted")
    rejected  = sum(1 for m in review.values() if m["status"] == "❌ Rejected")
    pending   = total - accepted - rejected

    # Summary bar
    sb1, sb2, sb3, sb4 = st.columns(4)
    sb1.metric("Total Fields", total)
    sb2.metric("✅ Accepted", accepted)
    sb3.metric("⏳ Pending", pending)
    sb4.metric("❌ Rejected", rejected)

    st.markdown("")

    # Filters
    fc1, fc2, fc3 = st.columns(3)
    with fc1:
        conf_filter = st.multiselect(
            "Filter by Confidence",
            ["HIGH", "MEDIUM", "LOW"],
            default=["HIGH", "MEDIUM", "LOW"],
            key="conf_filter",
        )
    with fc2:
        status_filter = st.multiselect(
            "Filter by Status",
            ["✅ Accepted", "⏳ Pending", "❌ Rejected"],
            default=["✅ Accepted", "⏳ Pending", "❌ Rejected"],
            key="status_filter",
        )
    with fc3:
        # Get unique SAP objects
        objects = sorted(set(m["sap_object"] for m in review.values()))
        obj_filter = st.multiselect(
            "Filter by SAP Object",
            objects,
            default=objects,
            key="obj_filter",
        )

    st.markdown("---")

    # Quick actions
    qa1, qa2, qa3 = st.columns(3)
    with qa1:
        if st.button("✅ Accept All HIGH confidence"):
            for i, m in review.items():
                if m["confidence"] == "HIGH":
                    review[i]["status"] = "✅ Accepted"
            st.session_state["mapper_review"] = review
            st.rerun()
    with qa2:
        if st.button("✅ Accept All Pending"):
            for i, m in review.items():
                if m["status"] == "⏳ Pending":
                    review[i]["status"] = "✅ Accepted"
            st.session_state["mapper_review"] = review
            st.rerun()
    with qa3:
        if st.button("🔄 Reset All to Pending"):
            for i in review:
                review[i]["status"] = "⏳ Pending"
            st.session_state["mapper_review"] = review
            st.rerun()

    st.markdown("---")

    # Group by SAP Object
    filtered = {
        i: m for i, m in review.items()
        if m["confidence"] in conf_filter
        and m["status"] in status_filter
        and m["sap_object"] in obj_filter
    }

    # Group by sap_object
    groups = {}
    for i, m in filtered.items():
        obj = m["sap_object"]
        if obj not in groups:
            groups[obj] = []
        groups[obj].append((i, m))

    for sap_object, items in groups.items():
        with st.expander(f"📦 {sap_object} — {len(items)} field(s)", expanded=True):
            for idx, (i, m) in enumerate(items):
                with st.container():
                    # Header row
                    h1c, h2c, h3c, h4c = st.columns([2, 2, 2, 1])
                    with h1c:
                        st.markdown(f"**`{m['legacy_field']}`**")
                        st.caption(m.get("legacy_description", ""))
                    with h2c:
                        arrow = "→"
                        if m["sap_table"] == "NO_MATCH":
                            st.markdown(f"**No SAP equivalent**")
                        else:
                            st.markdown(f"**`{m['sap_table']}.{m['sap_field']}`**")
                            st.caption(m.get("sap_description", ""))
                    with h3c:
                        st.markdown(
                            confidence_badge(m["confidence"]) + "&nbsp;&nbsp;" +
                            status_badge(m["status"]),
                            unsafe_allow_html=True,
                        )
                        st.caption(f"🔄 {m.get('transformation', '—')}")
                    with h4c:
                        # Action buttons
                        ac1, ac2, ac3 = st.columns(3)
                        with ac1:
                            if st.button("✅", key=f"acc_{i}", help="Accept"):
                                review[i]["status"] = "✅ Accepted"
                                st.session_state["mapper_review"] = review
                                st.rerun()
                        with ac2:
                            if st.button("❌", key=f"rej_{i}", help="Reject"):
                                review[i]["status"] = "❌ Rejected"
                                st.session_state["mapper_review"] = review
                                st.rerun()
                        with ac3:
                            edit_key = f"edit_mode_{i}"
                            if st.button("✏️", key=f"edit_{i}", help="Edit mapping"):
                                st.session_state[edit_key] = not st.session_state.get(edit_key, False)
                                st.rerun()

                    # Edit form (inline)
                    if st.session_state.get(f"edit_mode_{i}"):
                        with st.form(key=f"edit_form_{i}"):
                            e1, e2, e3 = st.columns(3)
                            with e1:
                                new_table = st.text_input("SAP Table", value=m["sap_table"], key=f"tbl_{i}")
                            with e2:
                                new_field = st.text_input("SAP Field", value=m["sap_field"], key=f"fld_{i}")
                            with e3:
                                new_transform = st.text_input("Transformation", value=m.get("transformation", ""), key=f"trn_{i}")
                            new_notes = st.text_input("Notes", value=m.get("reviewer_notes", ""), key=f"nts_{i}")
                            if st.form_submit_button("💾 Save", type="primary"):
                                review[i]["sap_table"]       = new_table
                                review[i]["sap_field"]       = new_field
                                review[i]["transformation"]  = new_transform
                                review[i]["reviewer_notes"]  = new_notes
                                review[i]["status"]          = "✅ Accepted"
                                st.session_state["mapper_review"] = review
                                st.session_state[f"edit_mode_{i}"] = False
                                st.rerun()

                    # Notes display
                    if m.get("notes"):
                        st.caption(f"ℹ️ {m['notes']}")

                    if idx < len(items) - 1:
                        st.markdown('<hr style="margin:6px 0;border-color:#2a2a3e;">', unsafe_allow_html=True)

    # ── Step 5: Export ────────────────────────────────────────────────────────
    st.divider()
    st.markdown("## Step 5 — Export Mapping Specification")

    export_filter = st.radio(
        "Export scope",
        ["All mappings", "Accepted only", "Pending + Accepted"],
        horizontal=True,
        key="export_filter",
    )

    if st.button("📥 Generate Excel Mapping Spec", type="primary"):
        rows = list(review.values())
        if export_filter == "Accepted only":
            rows = [r for r in rows if r["status"] == "✅ Accepted"]
        elif export_filter == "Pending + Accepted":
            rows = [r for r in rows if r["status"] != "❌ Rejected"]

        df_export = pd.DataFrame(rows, columns=[
            "legacy_field", "legacy_description", "legacy_type",
            "sap_object", "sap_table", "sap_field", "sap_description",
            "transformation", "confidence", "status", "reviewer_notes", "notes"
        ])
        df_export.columns = [
            "Legacy Field", "Legacy Description", "Legacy Type",
            "SAP Object", "SAP Table", "SAP Field", "SAP Field Description",
            "Transformation Rule", "AI Confidence", "Status", "Reviewer Notes", "Migration Notes"
        ]

        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine="openpyxl") as writer:
            df_export.to_excel(writer, sheet_name="Field Mapping", index=False)

            # Summary sheet
            summary_data = {
                "Metric": ["Legacy System", "SAP Module", "Total Fields", "Accepted", "Pending", "Rejected", "HIGH Confidence", "MEDIUM Confidence", "LOW Confidence"],
                "Value": [
                    st.session_state.get("mapper_system_final", "—"),
                    st.session_state.get("mapper_module_final", "—"),
                    total, accepted, pending, rejected,
                    sum(1 for m in review.values() if m["confidence"] == "HIGH"),
                    sum(1 for m in review.values() if m["confidence"] == "MEDIUM"),
                    sum(1 for m in review.values() if m["confidence"] == "LOW"),
                ]
            }
            pd.DataFrame(summary_data).to_excel(writer, sheet_name="Summary", index=False)

        buf.seek(0)
        legacy_sys = st.session_state.get("mapper_system_final", "Legacy").replace(" ", "_")
        st.download_button(
            label="⬇️ Download Mapping Spec Excel",
            data=buf,
            file_name=f"{legacy_sys}_to_SAP_Field_Mapping.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        st.success(f"✅ {len(df_export)} mappings exported.")
