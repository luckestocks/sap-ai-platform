"""
utils/llm_groq.py
Groq Llama 3.1 70B connector — fallback LLM for SAP AI Platform.
14,400 requests/day free tier. Text only — no vision support.
"""

import os
from groq import Groq
from typing import Optional


def _get_client() -> Groq:
    try:
        import streamlit as st
        api_key = st.secrets.get("GROQ_API_KEY", "")
    except Exception:
        api_key = ""
    if not api_key:
        api_key = os.getenv("GROQ_API_KEY", "")
    if not api_key:
        raise ValueError("GROQ_API_KEY not set in environment / .env")
    return Groq(api_key=api_key)


def groq_query(
    prompt: str,
    system_prompt: Optional[str] = None,
    temperature: float = 0.2,
    max_tokens: int = 2048,
) -> str:
    """
    Send a text prompt to Groq Llama 3.1 70B and return the response string.
    Note: Groq does not support vision/image input — text only.
    """
    client = _get_client()

    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    response = client.chat.completions.create(
        model="llama-3.1-70b-versatile",
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    return response.choices[0].message.content
