from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from .ai import compact_json, generate_text
from .news import get_topic_payload
from .prices import get_prices_payload
from .search import detect_intent, search_general_web, search_product_prices, summarize_search

LOCAL_TZ = timezone(timedelta(hours=7))


def _short_news_answer(topic_payload: dict[str, Any]) -> str:
    items = topic_payload.get("items", [])
    if not items:
        return f"Chưa có dữ liệu mới cho {topic_payload.get('label', 'chủ đề này')}."

    lines = [topic_payload.get("summary") or f"Tổng hợp nhanh cho {topic_payload.get('label', '')}:"]
    for item in items[:4]:
        source = item.get("source", "")
        title = item.get("title", "")
        if source:
            lines.append(f"- {title} ({source})")
        else:
            lines.append(f"- {title}")
    return "\n".join(lines)


def _short_prices_answer(prices_payload: dict[str, Any]) -> str:
    cards = prices_payload.get("cards", [])
    if not cards:
        return "Chưa lấy được bảng giá."

    lines = ["Bảng giá thị trường:"]
    for card in cards:
        label = card.get("label", "")
        price_text = card.get("price_text") or "chưa có dữ liệu"
        change_text = card.get("change_text") or ""
        lines.append(f"- {label}: {price_text} {card.get('unit', '')} {change_text}".strip())
    for card in prices_payload.get("vn_cards", []):
        label = card.get("label", "")
        price_text = card.get("price_text") or "chưa có dữ liệu"
        lines.append(f"- {label}: {price_text} {card.get('unit', '')}".strip())
    return "\n".join(lines)


def _format_sources(rows: list[dict[str, Any]]) -> list[dict[str, str]]:
    sources: list[dict[str, str]] = []
    seen: set[str] = set()
    for row in rows:
        url = str(row.get("url") or "")
        if not url or url in seen:
            continue
        seen.add(url)
        sources.append(
            {
                "title": str(row.get("title") or row.get("domain") or "Nguồn"),
                "url": url,
                "domain": str(row.get("domain") or ""),
                "snippet": str(row.get("snippet") or ""),
            }
        )
    return sources


def _build_ai_answer(question: str, context: dict[str, Any], fallback: str) -> str:
    prompt = f"""
Người dùng hỏi: {question}

Dữ liệu tham chiếu:
{compact_json(context, limit=5000)}

Hãy viết câu trả lời ngắn gọn bằng tiếng Việt.
Nếu có giá, ghi rõ đơn vị và nguồn tham khảo.
Nếu dữ liệu chưa đủ, nói rõ không đủ nguồn.
""".strip()
    text = generate_text(prompt, max_output_tokens=320)
    return text or fallback


def answer_question(question: str) -> dict[str, Any]:
    question = question.strip()
    if not question:
        return {
            "intent": "general",
            "answer": "Bạn hãy nhập một câu hỏi cụ thể.",
            "sources": [],
            "results": [],
            "generated_at": datetime.now(LOCAL_TZ).isoformat(),
        }

    detected = detect_intent(question)
    intent = detected["intent"]
    topic = detected["topic"] or "all"

    if intent == "news":
        topic_payload = get_topic_payload(topic)
        fallback = _short_news_answer(topic_payload)
        answer = _build_ai_answer(
            question,
            {"topic": topic_payload, "intent": intent},
            fallback,
        )
        return {
            "intent": intent,
            "topic": topic,
            "answer": answer,
            "sources": _format_sources(topic_payload.get("items", [])),
            "results": topic_payload.get("items", []),
            "generated_at": datetime.now(LOCAL_TZ).isoformat(),
        }

    if intent == "commodity":
        prices_payload = get_prices_payload()
        fallback = _short_prices_answer(prices_payload)
        answer = _build_ai_answer(
            question,
            {
                "prices": prices_payload.get("cards", []),
                "vn_prices": prices_payload.get("vn_cards", []),
                "intent": intent,
            },
            fallback,
        )
        sources = [
            {
                "title": card.get("label", ""),
                "url": str(card.get("source_url") or ""),
                "domain": "finance.yahoo.com",
                "snippet": f"{card.get('symbol', '')} {card.get('price_text', '')} {card.get('change_text', '')}".strip(),
            }
            for card in prices_payload.get("cards", [])
        ]
        for card in prices_payload.get("vn_cards", []):
            sources.append(
                {
                    "title": card.get("label", ""),
                    "url": str(card.get("source_url") or ""),
                    "domain": str(card.get("source_url") or "").replace("https://", "").split("/")[0],
                    "snippet": str(card.get("price_text") or ""),
                }
            )
        return {
            "intent": intent,
            "topic": "",
            "answer": answer,
            "sources": sources,
            "results": prices_payload.get("cards", []) + prices_payload.get("vn_cards", []),
            "generated_at": datetime.now(LOCAL_TZ).isoformat(),
        }

    if intent == "product":
        search_payload = search_product_prices(question)
        fallback = summarize_search(question, search_payload.get("results", []))
        answer = _build_ai_answer(
            question,
            {"search": search_payload, "intent": intent},
            fallback,
        )
        return {
            "intent": intent,
            "topic": "",
            "answer": answer,
            "sources": _format_sources(search_payload.get("results", [])),
            "results": search_payload.get("results", []),
            "generated_at": datetime.now(LOCAL_TZ).isoformat(),
        }

    search_payload = search_general_web(question)
    fallback = summarize_search(question, search_payload.get("results", []))
    answer = _build_ai_answer(
        question,
        {"search": search_payload, "intent": intent},
        fallback,
    )
    return {
        "intent": intent,
        "topic": "",
        "answer": answer,
        "sources": _format_sources(search_payload.get("results", [])),
        "results": search_payload.get("results", []),
        "generated_at": datetime.now(LOCAL_TZ).isoformat(),
    }

