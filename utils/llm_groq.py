"""
utils/llm_groq.py
Groq connector — default LLM + vision for SAP AI Platform.
Uses llama-3.3-70b-versatile for text, meta-llama/llama-4-scout-17b-16e-instruct for vision.
14,400 requests/day free tier.
"""

import os
import base64
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


def groq_vision_query(
    prompt: str,
    image_bytes: bytes,
    media_type: str = "image/png",
    system_prompt: Optional[str] = None,
) -> str:
    """
    Send an image + text prompt to Groq Vision (Llama 4 Scout).
    Supports screenshot OCR for SAP error analysis.
    """
    from groq import Groq
    client = Groq(api_key=_get_api_key())

    image_b64 = base64.b64encode(image_bytes).decode("utf-8")

    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})

    messages.append({
        "role": "user",
        "content": [
            {
                "type": "image_url",
                "image_url": {
                    "url": f"data:{media_type};base64,{image_b64}",
                },
            },
            {
                "type": "text",
                "text": prompt,
            },
        ],
    })

    response = client.chat.completions.create(
        model="meta-llama/llama-4-scout-17b-16e-instruct",
        messages=messages,
        max_tokens=2048,
    )
    return response.choices[0].message.content
