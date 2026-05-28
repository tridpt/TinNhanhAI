"""AI text generation layer supporting OpenAI and Google Gemini.

Provider selection is automatic based on which API key is set:
- ``GEMINI_API_KEY`` → Google Gemini (preferred if both are set)
- ``OPENAI_API_KEY`` → OpenAI Responses API

Set the model name via ``GEMINI_MODEL`` or ``OPENAI_MODEL`` env vars.
"""

from __future__ import annotations

import json
from typing import Any

import requests

import config

SYSTEM_PROMPT = """Bạn là trợ lý tin tức và tra cứu giá.
Trả lời ngắn gọn, rõ ràng, bằng tiếng Việt.
Không bịa số liệu. Nếu dữ liệu chưa đủ chắc chắn, nói rõ là "chưa đủ nguồn".
Khi tổng hợp tin tức, ưu tiên 3-5 ý chính. Khi trả lời giá, nêu nguồn và thời điểm cập nhật nếu có.
"""


def ai_enabled() -> bool:
    return bool(config.GEMINI_API_KEY or config.OPENAI_API_KEY)


def ai_provider() -> str:
    if config.GEMINI_API_KEY:
        return "gemini"
    if config.OPENAI_API_KEY:
        return "openai"
    return "none"


# --- Gemini -----------------------------------------------------------------------


def _generate_gemini(
    prompt: str,
    *,
    instructions: str,
    temperature: float,
    max_output_tokens: int,
) -> str:
    """Call Google Gemini generateContent endpoint."""

    model = config.GEMINI_MODEL
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}"
        f":generateContent?key={config.GEMINI_API_KEY}"
    )
    payload = {
        "contents": [
            {
                "parts": [{"text": f"{instructions}\n\n{prompt}"}],
            }
        ],
        "generationConfig": {
            "temperature": temperature,
            "maxOutputTokens": max_output_tokens,
        },
    }
    try:
        response = requests.post(url, json=payload, timeout=40)
        response.raise_for_status()
        data = response.json()
        return _extract_gemini_text(data)
    except Exception:
        return ""


def _extract_gemini_text(data: dict[str, Any]) -> str:
    """Pull text from Gemini's response structure."""

    candidates = data.get("candidates") or []
    if not candidates:
        return ""
    content = candidates[0].get("content") or {}
    parts = content.get("parts") or []
    texts = [str(part.get("text") or "") for part in parts if part.get("text")]
    return "\n".join(texts).strip()


# --- OpenAI -----------------------------------------------------------------------


def _generate_openai(
    prompt: str,
    *,
    instructions: str,
    temperature: float,
    max_output_tokens: int,
) -> str:
    """Call OpenAI Responses API."""

    payload = {
        "model": config.OPENAI_MODEL,
        "instructions": instructions,
        "input": prompt,
        "temperature": temperature,
        "max_output_tokens": max_output_tokens,
    }
    headers = {
        "Authorization": f"Bearer {config.OPENAI_API_KEY}",
        "Content-Type": "application/json",
    }
    try:
        response = requests.post(
            "https://api.openai.com/v1/responses",
            headers=headers,
            json=payload,
            timeout=40,
        )
        response.raise_for_status()
        data = response.json()
        return _extract_openai_text(data)
    except Exception:
        return ""


def _extract_openai_text(data: dict[str, Any]) -> str:
    text = data.get("output_text")
    if isinstance(text, str) and text.strip():
        return text.strip()

    chunks: list[str] = []
    for item in data.get("output", []) or []:
        for content in item.get("content", []) or []:
            content_type = content.get("type")
            if content_type in {"output_text", "text"}:
                value = content.get("text") or content.get("value")
                if value:
                    chunks.append(str(value))
    return "\n".join(chunks).strip()


# --- Public API -------------------------------------------------------------------


def generate_text(
    prompt: str,
    *,
    instructions: str = SYSTEM_PROMPT,
    temperature: float = 0.2,
    max_output_tokens: int = 400,
) -> str:
    """Generate text using the configured AI provider.

    Returns empty string if no provider is configured or the call fails.
    """

    provider = ai_provider()
    if provider == "gemini":
        return _generate_gemini(
            prompt,
            instructions=instructions,
            temperature=temperature,
            max_output_tokens=max_output_tokens,
        )
    if provider == "openai":
        return _generate_openai(
            prompt,
            instructions=instructions,
            temperature=temperature,
            max_output_tokens=max_output_tokens,
        )
    return ""


def compact_json(data: Any, limit: int = 5000) -> str:
    text = json.dumps(data, ensure_ascii=False, indent=2)
    if len(text) <= limit:
        return text
    return text[: limit - 120] + "\n... (đã rút gọn)"
