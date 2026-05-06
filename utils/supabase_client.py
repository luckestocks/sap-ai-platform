# utils/supabase_client.py
# SAP AI Platform — Phase 1
# Supabase connector: embeddings, RAG search, resolution logging, L3 anonymisation

import os
import re
from typing import Optional
from functools import lru_cache

from supabase import create_client, Client
from sentence_transformers import SentenceTransformer

# ── Connection ────────────────────────────────────────────────────────────────

@lru_cache(maxsize=1)
def get_supabase() -> Client:
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_ANON_KEY")
    if not url or not key:
        raise ValueError("SUPABASE_URL and SUPABASE_ANON_KEY must be set in Streamlit secrets.")
    return create_client(url, key)


# ── Embedding Model ───────────────────────────────────────────────────────────
# MiniLM L6 v2 — 384 dimensions, free, runs on Streamlit Cloud
# Cached so the model loads once per session

@lru_cache(maxsize=1)
def get_embedding_model() -> SentenceTransformer:
    return SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")


def embed_text(text: str) -> list[float]:
    """Generate a 384-dim embedding vector for any text string."""
    model = get_embedding_model()
    return model.encode(text, normalize_embeddings=True).tolist()


# ── RAG Search — 4-Level Hierarchy ───────────────────────────────────────────

def rag_search(
    query: str,
    project_id: str,
    client_id: str,
    l1_threshold: float = 0.75,
    l2_threshold: float = 0.75,
    l3_threshold: float = 0.70,
    match_count: int = 3,
) -> dict:
    """
    Run 4-level RAG search hierarchy.
    Returns: { level, label, colour, results[] } — stops at first level with hits.
    """
    supabase = get_supabase()
    embedding = embed_text(query)

    # L1 — Current project
    res = supabase.rpc(
        "match_project_errors",
        {
            "query_embedding": embedding,
            "match_project_id": project_id,
            "match_threshold": l1_threshold,
            "match_count": match_count,
        },
    ).execute()
    if res.data:
        return {"level": 1, "label": "Project KB", "colour": "blue", "results": res.data}

    # L2 — Same client, other projects
    res = supabase.rpc(
        "match_client_errors",
        {
            "query_embedding": embedding,
            "match_client_id": client_id,
            "exclude_project_id": project_id,
            "match_threshold": l2_threshold,
            "match_count": match_count,
        },
    ).execute()
    if res.data:
        return {"level": 2, "label": "Client KB", "colour": "green", "results": res.data}

    # L3 — Cross-client anonymised KB
    res = supabase.rpc(
        "match_cross_client_kb",
        {
            "query_embedding": embedding,
            "match_threshold": l3_threshold,
            "match_count": match_count,
        },
    ).execute()
    if res.data:
        return {"level": 3, "label": "Global KB", "colour": "yellow", "results": res.data}

    # L4 — No match found, caller falls back to LLM
    return {"level": 4, "label": "LLM Fallback", "colour": "white", "results": []}


# ── Resolution Logging ────────────────────────────────────────────────────────

def save_resolution(
    client_id: str,
    project_id: str,
    error_message: str,
    root_cause: str,
    fix_steps: str,
    error_type: str = "",
    error_code: str = "",
    t_codes: list[str] = None,
    load_phase: str = "",
    time_to_resolve: int = None,
    created_by: str = "",
) -> dict:
    """
    Save a resolved error to error_resolutions (L1/L2 source).
    Auto-promotes an anonymised copy to cross_client_kb (L3).
    Returns: { resolution_id, kb_id, status }
    """
    supabase = get_supabase()

    # Embed error message + actual fix steps
    # Using fix_steps (not root_cause) so different fixes for same error get distinct embeddings
    embed_input = f"{error_message}\n{fix_steps}"
    embedding = embed_text(embed_input)

    # Save to error_resolutions
    resolution_row = {
        "client_id": client_id,
        "project_id": project_id,
        "error_type": error_type,
        "error_code": error_code,
        "error_message": error_message,
        "root_cause": root_cause,
        "fix_steps": fix_steps,
        "t_codes": t_codes or [],
        "load_phase": load_phase,
        "time_to_resolve": time_to_resolve,
        "embedding": embedding,
        "created_by": created_by,
    }
    res = supabase.table("error_resolutions").insert(resolution_row).execute()
    resolution_id = res.data[0]["id"] if res.data else None

    # Auto-promote anonymised copy to cross_client_kb
    kb_id = None
    if resolution_id:
        anon = anonymise_for_kb(
            error_message=error_message,
            root_cause=root_cause,
            fix_steps=fix_steps,
        )
        kb_row = {
            "source_id": resolution_id,
            "error_type": error_type,
            "error_code": error_code,
            "error_message": anon["error_message"],
            "root_cause": anon["root_cause"],
            "fix_steps": anon["fix_steps"],
            "t_codes": t_codes or [],
            "load_phase": load_phase,
            "time_to_resolve": time_to_resolve,
            "embedding": embed_text(f"{anon['error_message']}\n{anon['fix_steps']}"),
        }
        kb_res = supabase.table("cross_client_kb").insert(kb_row).execute()
        kb_id = kb_res.data[0]["id"] if kb_res.data else None

    return {
        "resolution_id": resolution_id,
        "kb_id": kb_id,
        "status": "saved" if resolution_id else "error",
    }


# ── Anonymisation for L3 ──────────────────────────────────────────────────────

# Patterns that identify client-specific PII to strip
_PII_PATTERNS = [
    # Company codes, plant codes, sales orgs (4-char alphanumeric like 1000, IN01, ZPLM)
    (r'\b[A-Z0-9]{4}\b(?=\s*(company code|plant|sales org|storage loc|purch org))', '[CODE]'),
    # Z-objects (custom SAP objects starting with Z or Y)
    (r'\bZ[A-Z0-9_]{2,}\b', '[Z_OBJECT]'),
    (r'\bY[A-Z0-9_]{2,}\b', '[Y_OBJECT]'),
    # System/RFC names (common pattern: SID_CLNT or SID000)
    (r'\b[A-Z]{2,3}[0-9]{3}\b', '[SYSTEM_ID]'),
    # Explicit client/project markers
    (r'\b(client|project|company)\s*[:\-]?\s*["\']?[A-Za-z0-9\s\-_]{2,30}["\']?', '[CLIENT_REF]'),
    # Person names preceded by "by" or "assigned to" (rough heuristic)
    (r'(?i)(assigned to|fixed by|raised by|reported by)\s+[A-Z][a-z]+\s+[A-Z][a-z]+', r'\1 [TEAM_MEMBER]'),
]


def anonymise_for_kb(
    error_message: str,
    root_cause: str,
    fix_steps: str,
) -> dict:
    """Strip client/project PII from text before promoting to cross_client_kb."""

    def _strip(text: str) -> str:
        for pattern, replacement in _PII_PATTERNS:
            text = re.sub(pattern, replacement, text)
        return text

    return {
        "error_message": _strip(error_message),
        "root_cause": _strip(root_cause),
        "fix_steps": _strip(fix_steps),
    }


# ── Client / Project Helpers ──────────────────────────────────────────────────

def get_clients() -> list[dict]:
    supabase = get_supabase()
    res = supabase.table("clients").select("id, name").order("name").execute()
    return res.data or []


def get_projects(client_id: str) -> list[dict]:
    supabase = get_supabase()
    res = (
        supabase.table("projects")
        .select("id, name, description")
        .eq("client_id", client_id)
        .order("name")
        .execute()
    )
    return res.data or []


def create_client_record(name: str) -> Optional[str]:
    """Create a new client. Returns the new client ID."""
    supabase = get_supabase()
    res = supabase.table("clients").insert({"name": name}).execute()
    return res.data[0]["id"] if res.data else None


def create_project_record(client_id: str, name: str, description: str = "") -> Optional[str]:
    """Create a new project under a client. Returns the new project ID."""
    supabase = get_supabase()
    res = supabase.table("projects").insert({
        "client_id": client_id,
        "name": name,
        "description": description,
    }).execute()
    return res.data[0]["id"] if res.data else None


# ── Connection Health Check ───────────────────────────────────────────────────

def check_connection() -> dict:
    """Returns { connected: bool, client_count: int, resolution_count: int }"""
    try:
        supabase = get_supabase()
        clients = supabase.table("clients").select("id", count="exact").execute()
        resolutions = supabase.table("error_resolutions").select("id", count="exact").execute()
        return {
            "connected": True,
            "client_count": clients.count or 0,
            "resolution_count": resolutions.count or 0,
        }
    except Exception as e:
        return {"connected": False, "error": str(e)}
