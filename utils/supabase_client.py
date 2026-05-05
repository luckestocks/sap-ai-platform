"""
utils/supabase_client.py
Supabase connection module — PostgreSQL + pgvector RAG search.
"""

import os
from supabase import create_client, Client
from typing import Optional

_supabase_client: Optional[Client] = None

def init_supabase() -> Optional[Client]:
    """Initialise Supabase client. Returns None if not configured — app still starts."""
    global _supabase_client
    if _supabase_client:
        return _supabase_client
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_ANON_KEY")
    if not url or not key:
        return None
    _supabase_client = create_client(url, key)
    return _supabase_client

def get_db() -> Client:
    """Return Supabase client, raising if not configured."""
    client = init_supabase()
    if not client:
        raise ValueError("Supabase not configured. Set SUPABASE_URL and SUPABASE_ANON_KEY.")
    return client

SCHEMA_SQL = """
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS clients (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name        TEXT NOT NULL,
    code        TEXT NOT NULL UNIQUE,
    status      TEXT DEFAULT 'active',
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS projects (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id   UUID REFERENCES clients(id) ON DELETE CASCADE,
    name        TEXT NOT NULL,
    code        TEXT NOT NULL,
    status      TEXT DEFAULT 'active',
    load_phase  TEXT,
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(client_id, code)
);

CREATE TABLE IF NOT EXISTS team_members (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id  UUID REFERENCES projects(id) ON DELETE CASCADE,
    name        TEXT NOT NULL,
    role        TEXT,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS error_resolutions (
    id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id            UUID REFERENCES clients(id),
    project_id           UUID REFERENCES projects(id),
    error_text           TEXT NOT NULL,
    error_type           TEXT,
    root_cause           TEXT,
    fix_applied          TEXT,
    load_phase           TEXT,
    sap_object           TEXT,
    tool_used            TEXT,
    resolved_by          TEXT,
    resolution_time_mins INT,
    resolved_at          TIMESTAMPTZ DEFAULT NOW(),
    embedding            VECTOR(768)
);

CREATE TABLE IF NOT EXISTS cross_client_kb (
    id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    error_type           TEXT,
    root_cause           TEXT,
    fix_steps            TEXT,
    tcodes               TEXT[],
    load_phase           TEXT,
    resolution_time_mins INT,
    source_year          INT,
    embedding            VECTOR(768),
    created_at           TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS usage_logs (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tool        TEXT,
    provider    TEXT,
    client_id   UUID REFERENCES clients(id),
    project_id  UUID REFERENCES projects(id),
    query_text  TEXT,
    response_ms INT,
    tokens_used INT,
    logged_at   TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS error_resolutions_embedding_idx
    ON error_resolutions USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);

CREATE INDEX IF NOT EXISTS cross_client_kb_embedding_idx
    ON cross_client_kb USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);
"""

def print_schema():
    """Print schema SQL for manual execution in Supabase SQL editor."""
    print(SCHEMA_SQL)

def vector_search_project(
    embedding: list[float],
    client_id: str,
    project_id: str,
    limit: int = 3,
    threshold: float = 0.75,
) -> list[dict]:
    """L1 search — current project only."""
    db = get_db()
    response = db.rpc("match_project_errors", {
        "query_embedding": embedding,
        "match_client_id": client_id,
        "match_project_id": project_id,
        "match_threshold": threshold,
        "match_count": limit,
    }).execute()
    return response.data or []

def vector_search_client(
    embedding: list[float],
    client_id: str,
    exclude_project_id: str,
    limit: int = 3,
    threshold: float = 0.75,
) -> list[dict]:
    """L2 search — same client, other projects."""
    db = get_db()
    response = db.rpc("match_client_errors", {
        "query_embedding": embedding,
        "match_client_id": client_id,
        "exclude_project_id": exclude_project_id,
        "match_threshold": threshold,
        "match_count": limit,
    }).execute()
    return response.data or []

def vector_search_cross_client(
    embedding: list[float],
    limit: int = 3,
    threshold: float = 0.70,
) -> list[dict]:
    """L3 search — cross-client anonymised knowledge base."""
    db = get_db()
    response = db.rpc("match_cross_client_kb", {
        "query_embedding": embedding,
        "match_threshold": threshold,
        "match_count": limit,
    }).execute()
    return response.data or []

def save_resolution(resolution: dict) -> dict:
    """Save a confirmed resolution to the project-level store."""
    db = get_db()
    response = db.table("error_resolutions").insert(resolution).execute()
    return response.data[0] if response.data else {}

def promote_to_cross_client(resolution: dict) -> dict:
    """Anonymise a resolution and save to the cross-client knowledge base."""
    db = get_db()
    anon = {
        "error_type":           resolution.get("error_type"),
        "root_cause":           resolution.get("root_cause"),
        "fix_steps":            resolution.get("fix_applied"),
        "tcodes":               resolution.get("tcodes", []),
        "load_phase":           resolution.get("load_phase"),
        "resolution_time_mins": resolution.get("resolution_time_mins"),
        "source_year":          resolution.get("resolved_at", "")[:4] if resolution.get("resolved_at") else None,
        "embedding":            resolution.get("embedding"),
    }
    response = db.table("cross_client_kb").insert(anon).execute()
    return response.data[0] if response.data else {}
