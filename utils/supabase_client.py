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

@lru_cache(maxsize=1)
def get_embedding_model() -> SentenceTransformer:
    return SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")


def embed_text(text: str) -> list[float]:
    """Generate a 384-dim embedding vector for any text string."""
    model = get_embedding_model()
    return model.encode(text, normalize_embeddings=True).tolist()


# ── RAG Search — Additive Multi-Level ────────────────────────────────────────
#
# EMBEDDING DESIGN (critical):
#   Embeddings are stored and queried on ERROR MESSAGE ONLY.
#   fix_steps is metadata — NOT part of the embedding.
#   This aligns query space with stored embedding space so every resolution
#   for the same error scores equally high, regardless of fix length/content.
#   We search BY error pattern; different fixes are surfaced as separate results.
#
# SEARCH SCOPE:
#   No context  → L3 Global KB only (all clients, all projects)
#   Client only → L3 Global + L2 Client-wide
#   Client+Proj → L3 Global + L2 Client + L1 Project
#
#   All applicable levels searched additively.
#   Results are merged, deduplicated by fix_steps fingerprint, sorted by similarity.

def kb_search(
    query: str,
    project_id: str = None,
    client_id: str = None,
    threshold: float = 0.60,
    match_count: int = 10,
) -> dict:
    """
    Additive multi-level KB search.
    Returns ALL matching resolutions across all applicable levels.

    Each result dict includes:
        similarity, error_message, root_cause, fix_steps, t_codes,
        load_phase, error_type, error_code, client_name, project_name,
        kb_source  ('Global KB' | 'Client KB' | 'Project KB')
    """
    supabase  = get_supabase()
    # Normalise query: strip leading SAP error codes (E0001, ME123 etc.)
    # so "E0001 Partner profile not found" and "Partner profile not found"
    # embed to the same vector space and match each other above threshold.
    import re as _re
    normalised_query = _re.sub(r'^\s*[A-Z]{1,5}\d{3,5}\s*', '', query).strip()
    embedding = embed_text(normalised_query if normalised_query else query)

    all_results       = []
    levels_searched   = []
    seen_fingerprints = set()

    def _fingerprint(r: dict) -> str:
        # Deduplicate by fix content — same fix from multiple levels won't double-show
        return (r.get("fix_steps") or "")[:120].strip().lower()

    def _merge(rows: list[dict], kb_source: str):
        for r in rows:
            fp = _fingerprint(r)
            if fp not in seen_fingerprints:
                seen_fingerprints.add(fp)
                r["kb_source"] = kb_source
                all_results.append(r)

    # L3 — Cross-client Global KB (always searched)
    try:
        res = supabase.rpc("match_cross_client_kb", {
            "query_embedding": embedding,
            "match_threshold": threshold,
            "match_count": match_count,
        }).execute()
        if res.data:
            _merge(res.data, "Global KB")
            levels_searched.append("L3 Global")
    except Exception:
        pass

    # L1 — Project-specific
    if project_id:
        try:
            res = supabase.rpc("match_project_errors", {
                "query_embedding": embedding,
                "match_project_id": project_id,
                "match_threshold": threshold,
                "match_count": match_count,
            }).execute()
            if res.data:
                _merge(res.data, "Project KB")
                if "L1 Project" not in levels_searched:
                    levels_searched.append("L1 Project")
        except Exception:
            pass

    # L2 — Client-wide
    if client_id and project_id:
        try:
            res = supabase.rpc("match_client_errors", {
                "query_embedding": embedding,
                "match_client_id": client_id,
                "exclude_project_id": project_id,
                "match_threshold": threshold,
                "match_count": match_count,
            }).execute()
            if res.data:
                _merge(res.data, "Client KB")
                if "L2 Client" not in levels_searched:
                    levels_searched.append("L2 Client")
        except Exception:
            pass
    elif client_id:
        try:
            res = supabase.rpc("match_client_errors", {
                "query_embedding": embedding,
                "match_client_id": client_id,
                "exclude_project_id": "00000000-0000-0000-0000-000000000000",
                "match_threshold": threshold,
                "match_count": match_count,
            }).execute()
            if res.data:
                _merge(res.data, "Client KB")
                if "L2 Client" not in levels_searched:
                    levels_searched.append("L2 Client")
        except Exception:
            pass

    all_results.sort(key=lambda r: r.get("similarity", 0), reverse=True)

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
        "level": 3 if all_results else 4,
        "label": summary_label if all_results else "LLM Fallback",
    }


# ── Legacy wrapper ────────────────────────────────────────────────────────────

def rag_search(
    query: str,
    project_id: str = None,
    client_id: str = None,
    l1_threshold: float = 0.75,
    l2_threshold: float = 0.75,
    l3_threshold: float = 0.70,
    match_count: int = 10,
) -> dict:
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
    Auto-promotes anonymised copy to cross_client_kb (L3).

    If client_id or project_id is None / a zero UUID (e.g. from War Room
    with no project selected), skips error_resolutions (which has FK constraints)
    and pushes directly to cross_client_kb (L3) only.

    Embeddings use error_message only — aligns stored and query embedding spaces.
    """
    supabase  = get_supabase()

    # Normalise: strip leading SAP error codes before embedding
    # so "E0001 Partner profile not found" and "Partner profile not found"
    # produce identical embeddings and match each other in similarity search.
    import re as _re
    def _normalise(text: str) -> str:
        cleaned = _re.sub(r'^\s*[A-Z]{1,5}\d{3,5}\s*', '', text).strip()
        return cleaned if cleaned else text

    embedding = embed_text(_normalise(error_message))

    _NULL_UUID = "00000000-0000-0000-0000-000000000000"
    has_project = client_id and project_id and client_id != _NULL_UUID and project_id != _NULL_UUID

    resolution_id = None

    if has_project:
        # Full save: error_resolutions (L1/L2) + cross_client_kb (L3)
        resolution_row = {
            "client_id":      client_id,
            "project_id":     project_id,
            "error_type":     error_type,
            "error_code":     error_code,
            "error_message":  error_message,
            "root_cause":     root_cause,
            "fix_steps":      fix_steps,
            "t_codes":        t_codes or [],
            "load_phase":     load_phase,
            "time_to_resolve": time_to_resolve,
            "embedding":      embedding,
            "created_by":     created_by,
        }
        try:
            res = supabase.table("error_resolutions").insert(resolution_row).execute()
            resolution_id = res.data[0]["id"] if res.data else None
        except Exception:
            resolution_id = None

    # Always push to cross_client_kb (L3) — with or without a project
    kb_id = None
    try:
        anon = anonymise_for_kb(
            error_message=error_message,
            root_cause=root_cause,
            fix_steps=fix_steps,
        )
        kb_row = {
            "source_id":      resolution_id,   # None is fine — nullable FK
            "error_type":     error_type,
            "error_code":     error_code,
            "error_message":  anon["error_message"],
            "root_cause":     anon["root_cause"],
            "fix_steps":      anon["fix_steps"],
            "t_codes":        t_codes or [],
            "load_phase":     load_phase,
            "time_to_resolve": time_to_resolve,
            "embedding":      embed_text(_normalise(anon["error_message"])),
        }
        kb_res = supabase.table("cross_client_kb").insert(kb_row).execute()
        kb_id = kb_res.data[0]["id"] if kb_res.data else None
    except Exception:
        kb_id = None

    return {
        "resolution_id": resolution_id,
        "kb_id":         kb_id,
        "status":        "saved" if (resolution_id or kb_id) else "error",
    }

    return {
        "resolution_id": resolution_id,
        "kb_id": kb_id,
        "status": "saved" if resolution_id else "error",
    }


# ── Anonymisation for L3 ──────────────────────────────────────────────────────

_PII_PATTERNS = [
    (r'\b[A-Z0-9]{4}\b(?=\s*(company code|plant|sales org|storage loc|purch org))', '[CODE]'),
    (r'\bZ[A-Z0-9_]{2,}\b', '[Z_OBJECT]'),
    (r'\bY[A-Z0-9_]{2,}\b', '[Y_OBJECT]'),
    (r'\b[A-Z]{2,3}[0-9]{3}\b', '[SYSTEM_ID]'),
    (r'\b(client|project|company)\s*[:\-]?\s*["\']?[A-Za-z0-9\s\-_]{2,30}["\']?', '[CLIENT_REF]'),
    (r'(?i)(assigned to|fixed by|raised by|reported by)\s+[A-Z][a-z]+\s+[A-Z][a-z]+', r'\1 [TEAM_MEMBER]'),
]


def anonymise_for_kb(error_message: str, root_cause: str, fix_steps: str) -> dict:
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
    supabase = get_supabase()
    res = supabase.table("clients").insert({"name": name}).execute()
    return res.data[0]["id"] if res.data else None


def create_project_record(client_id: str, name: str, description: str = "") -> Optional[str]:
    supabase = get_supabase()
    res = supabase.table("projects").insert({
        "client_id": client_id,
        "name": name,
        "description": description,
    }).execute()
    return res.data[0]["id"] if res.data else None


# ── Connection Health Check ───────────────────────────────────────────────────

def check_connection() -> dict:
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


# ── Persistent Daily Groq Usage ───────────────────────────────────────────────
# Stored in app_state table (key='groq_usage') so it survives browser refreshes.
# Falls back to 0 gracefully if the table doesn't exist yet.

def get_groq_usage(today: str) -> int:
    """
    Return today's Groq call count from Supabase.
    If the stored date doesn't match today, returns 0 (new day = fresh counter).
    """
    try:
        supabase = get_supabase()
        res = supabase.table("app_state").select("value").eq("key", "groq_usage").execute()
        if res.data:
            stored = res.data[0]["value"]
            if stored.get("date") == today:
                return int(stored.get("calls", 0))
        return 0
    except Exception:
        return 0


def increment_groq_usage(today: str, increment: int = 1) -> int:
    """
    Add `increment` to today's Groq call count in Supabase.
    Returns the new total call count.
    Uses upsert so it works whether the row exists or not.
    """
    try:
        supabase = get_supabase()
        current   = get_groq_usage(today)
        new_count = current + increment
        supabase.table("app_state").upsert({
            "key":        "groq_usage",
            "value":      {"date": today, "calls": new_count},
            "updated_at": "now()",
        }).execute()
        return new_count
    except Exception:
        return 0
