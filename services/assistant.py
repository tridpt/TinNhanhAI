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

    label = topic_payload.get("label", "Tin tức")
    lines = [f"Điểm tin {label} hôm nay:"]
    for item in items[:5]:
        source = item.get("source", "")
        title = item.get("title", "")
        lines.append(f"• {title}" + (f" ({source})" if source else ""))
    if len(items) > 5:
        lines.append(f"\n→ Xem thêm {len(items) - 5} bài ở tab Nguồn.")
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
    # Only show top 4 VN cards in fallback to keep the answer concise.
    vn_cards = prices_payload.get("vn_cards", [])[:4]
    for card in vn_cards:
        label = card.get("label", "")
        price_text = card.get("price_text") or "chưa có dữ liệu"
        lines.append(f"- {label}: {price_text} {card.get('unit', '')}".strip())
    if len(prices_payload.get("vn_cards", [])) > 4:
        lines.append(f"  (và {len(prices_payload['vn_cards']) - 4} loại vàng khác)")
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

Dữ liệu tham chiếu (tin tức/giá/kết quả tìm kiếm):
{compact_json(context, limit=8000)}

Hãy viết câu trả lời CHI TIẾT bằng tiếng Việt, dựa hoàn toàn vào dữ liệu tham chiếu.
Yêu cầu:
- Mở đầu bằng 1-2 câu tổng quan nêu bức tranh chung.
- Sau đó liệt kê các ý chính dưới dạng gạch đầu dòng. Với mỗi ý:
  + In đậm cụm từ khóa/chủ đề của ý (dùng **...**).
  + Giải thích 2-3 câu: nêu bối cảnh, số liệu cụ thể (giá, %, thời gian, tên riêng)
    nếu có trong dữ liệu, và ý nghĩa/tác động.
- Nếu là tin tức, cố gắng bao quát NHIỀU chủ đề khác nhau có trong dữ liệu (6-10 ý),
  không bỏ sót tin quan trọng.
- Nếu có giá, ghi rõ con số, đơn vị, mức biến động và nguồn.
- Kết thúc bằng 1 câu nhận định ngắn nếu phù hợp.
- Tuyệt đối không bịa thông tin ngoài dữ liệu. Nếu dữ liệu chưa đủ, nói rõ.
""".strip()
    text = generate_text(prompt, max_output_tokens=1400, temperature=0.3)
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

