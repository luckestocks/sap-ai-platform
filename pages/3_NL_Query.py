"""
pages/3_NL_Query.py
Datasphere Insight Generator — plain English to SQL to answer + chart.
"""

import streamlit as st
from utils.llm_router import query_llm

st.set_page_config(
    page_title="NL Query | SAP AI Platform",
    page_icon="📊",
    layout="wide",
)

with open("components/styles.css") as f:
    st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)

st.markdown("# 📊 Datasphere NL Query")
st.markdown("Ask business questions in plain English — get SQL, answers, and charts. No SQL knowledge needed.")

st.info("🔧 **Phase 3 feature** — SQL generation works now. Live Datasphere REST API connects in Phase 3.", icon="ℹ️")

# ── Connection config ─────────────────────────────────────────────────────────
with st.expander("🔗 Datasphere Connection", expanded=False):
    ds_col1, ds_col2 = st.columns(2)
    with ds_col1:
        ds_url = st.text_input(
            "BTP Datasphere REST API URL",
            placeholder="https://<tenant>.ds.cfapps.<region>.hana.ondemand.com/api/v1",
        )
        ds_client_id = st.text_input("Client ID", type="password")
    with ds_col2:
        ds_space = st.text_input("Datasphere Space ID", placeholder="e.g. ANALYTICS_PROD")
        ds_client_secret = st.text_input("Client Secret", type="password")
    st.caption("Credentials stored in session only — not persisted. Configure permanently in Admin Panel.")

st.divider()

# ── Schema context ────────────────────────────────────────────────────────────
with st.expander("📋 View Schema Context (helps generate accurate SQL)", expanded=False):
    schema_context = st.text_area(
        "Paste your Datasphere view schema (field names + descriptions)",
        height=150,
        placeholder=(
            "V_STOCK_SAFETY: plant (string), material (string), avg_stock (decimal), "
            "safety_stock (decimal), quarter (string)\n"
            "V_PROCUREMENT: vendor (string), purchase_org (string), net_value (decimal), ..."
        ),
    )

st.divider()

# ── Query input ───────────────────────────────────────────────────────────────
question = st.text_area(
    "Ask your business question",
    height=120,
    placeholder=(
        "E.g.:\n"
        "Which plants had inventory below safety stock levels last quarter?\n"
        "Show me the top 10 vendors by purchase order value in 2025.\n"
        "What is the trend in GL posting volumes by cost centre this year?"
    ),
)

ask_btn = st.button(
    "🔍 Generate Insight",
    type="primary",
    disabled=not question.strip(),
)

# ── Results ───────────────────────────────────────────────────────────────────
if ask_btn and question.strip():

    with st.spinner("Generating SQL from your question..."):
        sql_prompt = (
            f"You are an expert in SAP Datasphere SQL.\n"
            f"Schema context:\n{schema_context or 'No schema provided — use reasonable field name assumptions.'}\n\n"
            f"Question: {question}\n\n"
            f"Generate a valid Datasphere-compatible SQL query to answer this question. "
            f"Return ONLY the SQL, no explanation, no markdown backticks."
        )
        sql_response, provider = query_llm(sql_prompt)
        sql_clean = sql_response.strip().replace("```sql", "").replace("```", "").strip()

    st.markdown("### Generated SQL")
    st.code(sql_clean, language="sql")

    st.divider()
    st.markdown("### Result")

    if not ds_url or not ds_client_id:
        st.warning(
            "⚠️ No Datasphere connection configured. "
            "Showing AI-simulated answer — connect your BTP space in Phase 3 for live data."
        )
        with st.spinner("Generating demo answer..."):
            demo_prompt = (
                f"You are an SAP analytics expert. The user asked: '{question}'\n"
                f"The SQL generated was:\n{sql_clean}\n\n"
                f"Simulate a realistic, specific answer as if this ran against real SAP data. "
                f"Use specific numbers, plant codes, vendor names, dates. "
                f"End with: 'Chart type recommended: [bar/line/pie] — reason: [one line]'"
            )
            demo_answer, _ = query_llm(demo_prompt)

        st.markdown("#### 🔮 Simulated Answer *(no live DB — for demo purposes)*")
        st.markdown(demo_answer)
        st.caption(f"Powered by {provider} — connect Datasphere in Phase 3 for live results")

    else:
        # Phase 3: Execute SQL via Datasphere REST API
        # 1. POST to OAuth token endpoint → get bearer token
        # 2. POST SQL to /api/v1/dwc/catalog/sources/{space}/data
        # 3. Parse JSON → DataFrame → Plotly chart
        st.info("🔧 Datasphere REST API execution — coming in Phase 3.")
