"""
utils/llm_claude.py
Anthropic Claude Sonnet 4.6 connector — premium LLM for SAP AI Platform.
"""

import os
import base64
import anthropic
from typing import Optional


def _get_client() -> anthropic.Anthropic:
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY not set in environment / .env")
    return anthropic.Anthropic(api_key=api_key)


def claude_query(
    prompt: str,
    system_prompt: Optional[str] = None,
    temperature: float = 0.2,
    max_tokens: int = 2048,
) -> str:
    """
    Send a text prompt to Claude Sonnet 4.6 and return the response string.
    """
    client = _get_client()
    kwargs = {
        "model": "claude-sonnet-4-6",
        "max_tokens": max_tokens,
        "temperature": temperature,
        "messages": [{"role": "user", "content": prompt}],
    }
    if system_prompt:
        kwargs["system"] = system_prompt
    response = client.messages.create(**kwargs)
    return response.content[0].text


def claude_vision_query(
    prompt: str,
    image_bytes: bytes,
    media_type: str = "image/png",
    system_prompt: Optional[str] = None,
) -> str:
    """
    Send an image + text prompt to Claude Vision.
    """
    client = _get_client()
    image_content = {
        "type": "image",
        "source": {
            "type": "base64",
            "media_type": media_type,
            "data": base64.b64encode(image_bytes).decode("utf-8"),
        },
    }
    kwargs = {
        "model": "claude-sonnet-4-6",
        "max_tokens": 2048,
        "temperature": 0.1,
        "messages": [
            {
                "role": "user",
                "content": [image_content, {"type": "text", "text": prompt}],
            }
        ],
    }
    if system_prompt:
        kwargs["system"] = system_prompt
    response = client.messages.create(**kwargs)
    return response.content[0].text
