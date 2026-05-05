# ⚡ SAP AI Platform

> Three RAG-powered AI tools for SAP Data Migration & Analytics professionals

**Author:** Kishore — SAP Data Migration Lead → SAP BTP + AI Senior Consultant  
**Stack:** Streamlit · Gemini Flash · Claude Sonnet 4.6 · Groq · Supabase + pgvector  
**Status:** Phase 0 Complete — Phase 1 Building

---

## Tools

| # | Tool | Purpose | Status |
|---|------|---------|--------|
| 1 | **SAP Migration Error Analyzer** | Diagnose SAP load errors with 4-level RAG knowledge hierarchy | Phase 1 |
| 2 | **SAP Data Quality Checker** | Score and flag data quality issues in migration extracts | Phase 2 |
| 3 | **Datasphere NL Query** | Plain English → SQL → answer + Plotly chart | Phase 3 |

---

## Architecture

**RAG — confirmed final for v1.**

4-Level Knowledge Hierarchy:
- 🟦 **L1** — Current project errors and fixes
- 🟩 **L2** — Same client, other projects
- 🟨 **L3** — Cross-client anonymised knowledge base (auto-promoted, PII stripped)
- ⬜ **L4** — LLM fallback (Gemini / Claude / Groq)

Every answer shows exactly which level answered it. Knowledge base grows automatically as your team logs resolutions.

---

## Tech Stack

| Layer | Technology | Cost |
|-------|-----------|------|
| UI | Streamlit | Free |
| Default LLM | Google Gemini Flash | Free tier |
| Premium LLM | Claude Sonnet 4.6 | ~$0.01–0.02/query |
| Fallback LLM | Groq Llama 3.1 70B | Free — 14,400 req/day |
| Screenshot OCR | Gemini Vision | Free tier |
| Vector DB | Supabase + pgvector | Free tier |
| Relational DB | Supabase PostgreSQL | Free tier |
| Hosting | Streamlit Community Cloud | Free |

---

## Project Structure

sap-ai-platform/
├── app.py                                        # Home page
├── requirements.txt
├── .env.example                                  # API key template
├── pages/
│   ├── 1_SAP_Data_Migration_Error_Analyzer.py   # Tool 1
│   ├── 2_SAP_Data_Migration_Data_Quality_Checker.py  # Tool 2
│   ├── 3_NL_Query.py                            # Tool 3
│   └── 4_Admin_Panel.py                         # Admin
├── utils/
│   ├── llm_router.py       # Unified LLM router + auto-fallback
│   ├── llm_gemini.py       # Gemini Flash connector
│   ├── llm_claude.py       # Claude Sonnet 4.6 connector
│   ├── llm_groq.py         # Groq fallback connector
│   ├── supabase_client.py  # DB + pgvector RAG helpers
│   ├── file_loader.py      # CSV/Excel/image upload utilities
│   └── response_renderer.py # Confidence badges, source labels
├── components/
│   └── styles.css          # Dark theme
└── .streamlit/
└── config.toml         # Theme config

---

## Build Roadmap

| Phase | What | Status |
|-------|------|--------|
| **Phase 0** | Skeleton — all connectors, structure, UI shell | ✅ Done |
| **Phase 1** | Error Analyzer — full RAG hierarchy, error classification | 🔨 Building |
| **Phase 2** | Data Quality Checker — Pandas + LLM validation layers | ⏳ Planned |
| **Phase 3** | Datasphere NL Query — REST API + Plotly charts | ⏳ Planned |
| **Phase 4** | Full Admin Panel | ⏳ Planned |
| **Phase 5** | Deploy + portfolio launch | ⏳ Planned |

---

*Built by Sparky — SAP Data Migration Lead pivoting to SAP BTP + AI Senior Consultant*  
*IITM Pravartak Advanced Certificate in Applied AI & Deep Learning*
