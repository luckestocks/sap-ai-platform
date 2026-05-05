"""
utils/llm_router.py
Unified LLM router for SAP AI Platform.
Routes to correct LLM based on admin setting. Auto-falls back to Groq on failure.
"""

import streamlit as st
from typing import Optional
from utils.llm_gemini import gemini_query, gemini_vision_query
from utils.llm_claude import claude_query, claude_vision_query
from utils.llm_groq   import groq_query

PROVIDER_LABELS = {
    "gemini": "🟢 Gemini Flash",
    "claude": "🟣 Claude Sonnet 4.6",
    "groq":   "🟠 Groq Llama 3.1 70B",
}

def get_active_provider() -> str:
    return st.session_state.get("llm_provider", "gemini")

def query_llm(
    prompt: str,
    system_prompt: Optional[str] = None,
    temperature: float = 0.2,
    max_tokens: int = 2048,
    force_provider: Optional[str] = None,
) -> tuple[str, str]:
    """
    Route a text query to the active LLM with automatic Groq fallback.
    Returns: (response_text, provider_used)
    """
    provider = force_provider or get_active_provider()

    try:
        if provider == "gemini":
            return gemini_query(prompt, system_prompt, temperature, max_tokens), "gemini"
        elif provider == "claude":
            return claude_query(prompt, system_prompt, temperature, max_tokens), "claude"
        elif provider == "groq":
            return groq_query(prompt, system_prompt, temperature, max_tokens), "groq"
        else:
            raise ValueError(f"Unknown provider: {provider}")

    except Exception as primary_err:
        if provider != "groq":
            try:
                result = groq_query(prompt, system_prompt, temperature, max_tokens)
                st.warning(
                    f"⚠️ {PROVIDER_LABELS[provider]} unavailable — fell back to Groq. "
                    f"Error: {primary_err}"
                )
                return result, "groq"
            except Exception as fallback_err:
                raise RuntimeError(
                    f"All LLM providers failed.\n"
                    f"Primary ({provider}): {primary_err}\n"
                    f"Fallback (groq): {fallback_err}"
                ) from fallback_err
        else:
            raise

def query_llm_vision(
    prompt: str,
    image_bytes: bytes,
    media_type: str = "image/png",
    system_prompt: Optional[str] = None,
    force_provider: Optional[str] = None,
) -> tuple[str, str]:
    """
    Route a vision query to the active LLM.
    Groq doesn't support vision — falls back to Gemini automatically.
    Returns: (response_text, provider_used)
    """
    provider = force_provider or get_active_provider()

    if provider == "groq":
        provider = "gemini"
        st.info("ℹ️ Groq doesn't support vision — using Gemini Flash for screenshot analysis.")

    try:
        if provider == "gemini":
            return gemini_vision_query(prompt, image_bytes, media_type, system_prompt), "gemini"
        elif provider == "claude":
            return claude_vision_query(prompt, image_bytes, media_type, system_prompt), "claude"

    except Exception as e:
        if provider != "gemini":
            try:
                result = gemini_vision_query(prompt, image_bytes, media_type, system_prompt)
                st.warning(f"⚠️ Claude Vision failed — fell back to Gemini Vision. Error: {e}")
                return result, "gemini"
            except Exception as fallback_err:
                raise RuntimeError(
                    f"All vision providers failed.\n"
                    f"Primary ({provider}): {e}\n"
                    f"Fallback (gemini): {fallback_err}"
                ) from fallback_err
        raise
