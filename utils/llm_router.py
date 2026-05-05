"""
utils/llm_router.py
Unified LLM router for SAP AI Platform.
Default: Groq Llama 3.3 70B (text + vision)
Premium: Claude Sonnet 4.6 (text + vision)
"""

import streamlit as st
from typing import Optional
from utils.llm_groq import groq_query, groq_vision_query
from utils.llm_claude import claude_query, claude_vision_query

PROVIDER_LABELS = {
    "groq":   "🟠 Groq Llama 3.3 70B",
    "claude": "🟣 Claude Sonnet 4.6",
}


def get_active_provider() -> str:
    return st.session_state.get("llm_provider", "groq")


def query_llm(
    prompt: str,
    system_prompt: Optional[str] = None,
    temperature: float = 0.2,
    max_tokens: int = 2048,
    force_provider: Optional[str] = None,
) -> tuple:
    """
    Route a text query to the active LLM.
    Groq is default. Claude is premium.
    Falls back to Groq if Claude fails.
    Returns: (response_text, provider_used)
    """
    provider = force_provider or get_active_provider()

    try:
        if provider == "claude":
            return claude_query(prompt, system_prompt, temperature, max_tokens), "claude"
        else:
            return groq_query(prompt, system_prompt, temperature, max_tokens), "groq"

    except Exception as primary_err:
        if provider == "claude":
            try:
                result = groq_query(prompt, system_prompt, temperature, max_tokens)
                st.warning(
                    f"⚠️ Claude unavailable — fell back to Groq. "
                    f"Error: {primary_err}"
                )
                return result, "groq"
            except Exception as fallback_err:
                raise RuntimeError(
                    f"All LLM providers failed.\n"
                    f"Claude: {primary_err}\n"
                    f"Groq: {fallback_err}"
                ) from fallback_err
        else:
            raise


def query_llm_vision(
    prompt: str,
    image_bytes: bytes,
    media_type: str = "image/png",
    system_prompt: Optional[str] = None,
    force_provider: Optional[str] = None,
) -> tuple:
    """
    Route a vision query to the active LLM.
    Both Groq and Claude support vision.
    Falls back to Groq if Claude fails.
    Returns: (response_text, provider_used)
    """
    provider = force_provider or get_active_provider()

    try:
        if provider == "claude":
            return claude_vision_query(prompt, image_bytes, media_type, system_prompt), "claude"
        else:
            return groq_vision_query(prompt, image_bytes, media_type, system_prompt), "groq"

    except Exception as primary_err:
        if provider == "claude":
            try:
                result = groq_vision_query(prompt, image_bytes, media_type, system_prompt)
                st.warning(
                    f"⚠️ Claude Vision failed — fell back to Groq Vision. "
                    f"Error: {primary_err}"
                )
                return result, "groq"
            except Exception as fallback_err:
                raise RuntimeError(
                    f"All vision providers failed.\n"
                    f"Claude: {primary_err}\n"
                    f"Groq: {fallback_err}"
                ) from fallback_err
        else:
            raise
