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
    return bool(config.OPENAI_API_KEY)


def _extract_output_text(data: dict[str, Any]) -> str:
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


def generate_text(
    prompt: str,
    *,
    instructions: str = SYSTEM_PROMPT,
    temperature: float = 0.2,
    max_output_tokens: int = 400,
) -> str:
    if not ai_enabled():
        return ""

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
        return _extract_output_text(data)
    except Exception:
        return ""


def compact_json(data: Any, limit: int = 5000) -> str:
    text = json.dumps(data, ensure_ascii=False, indent=2)
    if len(text) <= limit:
        return text
    return text[: limit - 120] + "\n... (đã rút gọn)"

