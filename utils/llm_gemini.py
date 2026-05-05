"""
utils/llm_gemini.py
Google Gemini Flash connector — default LLM for SAP AI Platform.
Handles text and vision (screenshot OCR) requests.
"""

import os
import base64
import google.generativeai as genai
from typing import Optional


def _get_api_key() -> str:
    """Read Gemini API key from Streamlit secrets or environment variable."""
    try:
        import streamlit as st
        key = st.secrets.get("GEMINI_API_KEY", "")
        if key:
            return key
    except Exception:
        pass
    key = os.getenv("GEMINI_API_KEY", "")
    if not key:
        raise ValueError("GEMINI_API_KEY not set in Streamlit secrets or environment")
    return key


def _get_client() -> genai.GenerativeModel:
    api_key = _get_api_key()
    genai.configure(api_key=api_key)
    return genai.GenerativeModel("gemini-1.5-flash")


def gemini_query(
    prompt: str,
    system_prompt: Optional[str] = None,
    temperature: float = 0.2,
    max_tokens: int = 2048,
) -> str:
    """
    Send a text prompt to Gemini Flash and return the response string.
    """
    model = _get_client()
    full_prompt = f"{system_prompt}\n\n{prompt}" if system_prompt else prompt
    response = model.generate_content(
        full_prompt,
        generation_config=genai.types.GenerationConfig(
            temperature=temperature,
            max_output_tokens=max_tokens,
        ),
    )
    return response.text


def gemini_vision_query(
    prompt: str,
    image_bytes: bytes,
    mime_type: str = "image/png",
    system_prompt: Optional[str] = None,
) -> str:
    """
    Send an image + text prompt to Gemini Flash Vision (for screenshot OCR).
    """
    model = _get_client()
    full_prompt = f"{system_prompt}\n\n{prompt}" if system_prompt else prompt
    image_part = {
        "mime_type": mime_type,
        "data": base64.b64encode(image_bytes).decode("utf-8"),
    }
    response = model.generate_content(
        [full_prompt, image_part],
        generation_config=genai.types.GenerationConfig(
            temperature=0.1,
            max_output_tokens=2048,
        ),
    )
    return response.text
