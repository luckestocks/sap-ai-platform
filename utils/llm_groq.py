"""
utils/llm_groq.py
Groq Llama 3.3 70B connector — fallback LLM for SAP AI Platform.
14,400 requests/day free tier. Text only — no vision support.
"""

import os
from typing import Optional


def _get_api_key() -> str:
    try:
        import streamlit as st
        key = st.secrets.get("GROQ_API_KEY", "")
        if key:
            return key
    except Exception:
        pass
    key = os.getenv("GROQ_API_KEY", "")
    if not key:
        raise ValueError("GROQ_API_KEY not set in environment / .env")
    return key


def groq_query(
    prompt: str,
    system_prompt: Optional[str] = None,
    temperature: float = 0.2,
    max_tokens: int = 2048,
) -> str:
    """
    Send a text prompt to Groq Llama 3.3 70B and return the response string.
    Note: Groq does not support vision/image input — text only.
    """
    from groq import Groq
    client = Groq(api_key=_get_api_key())

    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    return response.choices[0].message.content
