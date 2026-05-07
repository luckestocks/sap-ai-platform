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


# ── RAG Search — Additive Multi-Level ────────────────────────────────────────
#
# Design intent: this is a KNOWLEDGE BASE, not a decision tree.
# We search ALL applicable levels and return ALL matching resolutions,
# merged and deduplicated. The same error can have multiple resolutions
# across different projects/clients — we want every one of them surfaced.
#
# Search scope:
#   No client/project   → L3 Global KB only
#   Client only         → L3 Global + L2 Client-wide
#   Client + Project    → L3 Global + L2 Client-wide + L1 Project-specific
#
# Results are merged, deduplicated by fix fingerprint, sorted by similarity.
# Each result carries a 'kb_source' field ('Global KB', 'Client KB', 'Project KB')
# so the UI can show where each match came from.

def kb_search(
    query: str,
    project_id: str = None,
    client_id: str = None,
    threshold: float = 0.65,
    match_count: int = 10,
) -> dict:
    """
    Additive multi-level KB search.

    Returns:
        {
            "results": [ list of result dicts, sorted by similarity desc ],
            "levels_searched": [ list of level labels ],
            "summary_label": str   # e.g. "Global KB" / "Client KB" / "Project KB"
        }

    Each result dict has:
        similarity, error_message, root_cause, fix_steps, t_codes,
        load_phase, error_type, error_code, client_name, project_name,
        kb_source  ← which level this result came from
    """
    supabase  = get_supabase()
    embedding = embed_text(query)

    all_results    = []
    levels_searched = []
    seen_fingerprints = set()   # deduplicate by (error_message[:80] + fix[:80])

    def _fingerprint(r: dict) -> str:
        msg = (r.get("error_message") or "")[:80].strip().lower()
        fix = (r.get("fix_steps") or "")[:80].strip().lower()
        return f"{msg}||{fix}"

    def _merge(rows: list[dict], kb_source: str):
        for r in rows:
            fp = _fingerprint(r)
            if fp not in seen_fingerprints:
                seen_fingerprints.add(fp)
                r["kb_source"] = kb_source
                all_results.append(r)

    # ── L3 — Cross-client Global KB (always searched) ─────────────────────────
    try:
        res = supabase.rpc(
            "match_cross_client_kb",
            {
                "query_embedding": embedding,
                "match_threshold": threshold,
                "match_count": match_count,
            },
        ).execute()
        if res.data:
            _merge(res.data, "Global KB")
            levels_searched.append("L3 Global")
    except Exception:
        pass

    # ── L1 — Project-specific (only if project selected) ─────────────────────
    if project_id:
        try:
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
                _merge(res.data, "Project KB")
                if "L1 Project" not in levels_searched:
                    levels_searched.append("L1 Project")
        except Exception:
            pass

    # ── L2 — Client-wide, other projects (only if client selected) ───────────
    if client_id and project_id:
        try:
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
                _merge(res.data, "Client KB")
                if "L2 Client" not in levels_searched:
                    levels_searched.append("L2 Client")
        except Exception:
            pass
    elif client_id:
        # Client selected but no project — search all projects for this client
        try:
            res = supabase.rpc(
                "match_client_errors",
                {
                    "query_embedding": embedding,
                    "match_client_id": client_id,
                    "exclude_project_id": "00000000-0000-0000-0000-000000000000",  # exclude nothing
                    "match_threshold": threshold,
                    "match_count": match_count,
                },
            ).execute()
            if res.data:
                _merge(res.data, "Client KB")
                if "L2 Client" not in levels_searched:
                    levels_searched.append("L2 Client")
        except Exception:
            pass

    # Sort all results by similarity descending
    all_results.sort(key=lambda r: r.get("similarity", 0), reverse=True)

    # Determine summary label for badge display
    if project_id and client_id:
        summary_label = "Project + Client + Global KB"
    elif client_id:
        summary_label = "Client + Global KB"
    else:
        summary_label = "Global KB"

    return {
        "results": all_results,
        "levels_searched": levels_searched,
        "summary_label": summary_label,
        # Legacy fields — kept so old callers don't break
        "level": 3 if all_results else 4,
        "label": summary_label if all_results else "LLM Fallback",
    }


# ── Legacy wrapper — kept for backward compatibility ──────────────────────────
# rag_search() in utils/supabase_client.py is still imported by Admin Panel etc.
# It now delegates to kb_search() but returns the old waterfall shape.

def rag_search(
    query: str,
    project_id: str = None,
    client_id: str = None,
    l1_threshold: float = 0.75,
    l2_threshold: float = 0.75,
    l3_threshold: float = 0.70,
    match_count: int = 10,
) -> dict:
    """
    Legacy wrapper — delegates to kb_search().
    Returns: { level, label, colour, results[] }
    """
    result = kb_search(
        query=query,
        project_id=project_id,
        client_id=client_id,
        threshold=min(l1_threshold, l2_threshold, l3_threshold),
        match_count=match_count,
    )
    level = result["level"]
    colour_map = {1: "blue", 2: "green", 3: "yellow", 4: "white"}
    return {
        "level": level,
        "label": result["label"],
        "colour": colour_map.get(level, "white"),
        "results": result["results"],
    }


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
