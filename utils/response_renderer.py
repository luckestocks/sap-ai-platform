"""
utils/response_renderer.py
Formatted response renderer — confidence badges, source labels, T-code panels.
"""

import streamlit as st
from typing import Optional

CONFIDENCE_CONFIG = {
    "high":   {"emoji": "🟢", "label": "HIGH",   "css": "badge-high"},
    "medium": {"emoji": "🟡", "label": "MEDIUM", "css": "badge-medium"},
    "low":    {"emoji": "🔴", "label": "LOW",    "css": "badge-low"},
}

SOURCE_CONFIG = {
    "l1": {"css": "source-l1", "emoji": "🟦", "label": "Current Project"},
    "l2": {"css": "source-l2", "emoji": "🟩", "label": "Same Client — Other Project"},
    "l3": {"css": "source-l3", "emoji": "🟨", "label": "Cross-Project Knowledge"},
    "l4": {"css": "source-l4", "emoji": "⬜", "label": "LLM General Knowledge"},
}

ERROR_TYPE_COLORS = {
    "IDoc":  "#3b82f6",
    "BODS":  "#8b5cf6",
    "LTMC":  "#06b6d4",
    "LSMW":  "#10b981",
    "SDI":   "#f59e0b",
    "BAPI":  "#ef4444",
    "RFC":   "#ec4899",
    "SM21":  "#64748b",
}


def render_confidence_badge(level: str) -> None:
    """Render a 🟢/🟡/🔴 confidence badge."""
    cfg = CONFIDENCE_CONFIG.get(level.lower(), CONFIDENCE_CONFIG["low"])
    st.markdown(
        f'<span class="{cfg["css"]}">{cfg["emoji"]} Confidence: {cfg["label"]}</span>',
        unsafe_allow_html=True,
    )


def render_source_label(level: str, detail: str = "") -> None:
    """Render a source transparency label showing where the answer came from."""
    cfg = SOURCE_CONFIG.get(level, SOURCE_CONFIG["l4"])
    detail_str = f" — {detail}" if detail else ""
    st.markdown(
        f'<div class="source-label {cfg["css"]}">'
        f'{cfg["emoji"]} {cfg["label"]}{detail_str}'
        f'</div>',
        unsafe_allow_html=True,
    )


def render_tcode_panel(tcodes: list) -> None:
    """Render a horizontal list of T-code pills."""
    if not tcodes:
        return
    st.markdown("**Relevant T-Codes:**")
    pills_html = " ".join(
        f'<span class="tcode-pill">{t}</span>' for t in tcodes
    )
    st.markdown(f'<div>{pills_html}</div>', unsafe_allow_html=True)


def render_response_card(
    response_text: str,
    confidence: Optional[str] = None,
    source_level: Optional[str] = None,
    source_detail: Optional[str] = None,
    tcodes: Optional[list] = None,
    provider_used: Optional[str] = None,
) -> None:
    """Render a complete LLM response card with all metadata."""
    provider_icons = {
        "gemini": "🟢 Gemini Flash",
        "claude": "🟣 Claude Sonnet 4.6",
        "groq":   "🟠 Groq Llama 3.1 70B",
    }
    with st.container():
        meta_col1, meta_col2 = st.columns([2, 1])
        with meta_col1:
            if source_level:
                render_source_label(source_level, source_detail)
        with meta_col2:
            if confidence:
                render_confidence_badge(confidence)
        st.markdown(response_text)
        if tcodes:
            render_tcode_panel(tcodes)
        if provider_used:
            st.caption(f"Answered by {provider_icons.get(provider_used, provider_used)}")


def render_error_type_badge(error_type: str) -> None:
    """Render a coloured error type badge."""
    color = ERROR_TYPE_COLORS.get(error_type, "#64748b")
    st.markdown(
        f'<span style="background:{color}22; border:1px solid {color}55; '
        f'color:{color}; padding:0.2rem 0.6rem; border-radius:4px; '
        f'font-family:monospace; font-size:0.8rem; font-weight:600;">'
        f'{error_type}</span>',
        unsafe_allow_html=True,
    )
