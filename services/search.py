from __future__ import annotations

import json
import re
import unicodedata
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup
from ddgs import DDGS

import config

from .ai import compact_json, generate_text
from .cache import TTLCache

CACHE = TTLCache(namespace="search")
USER_AGENT = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) TinNhanhAI/1.0"}
# Build the allowlist from the same retailer config the UI advertises so adding
# a site in one place doesn't silently leave it filtered out here.
PRICE_DOMAIN_ALLOWLIST = tuple(item["domain"] for item in config.RETAIL_SEARCH_SITES)
PRICE_KEYWORDS = {
    "gia",
    "bao nhieu",
    "price",
    "mua",
    "phone",
    "dien thoai",
    "iphone",
    "samsung",
    "oppo",
    "xiaomi",
    "vivo",
    "laptop",
    "tablet",
    "tai nghe",
    "smartwatch",
    "may anh",
}
NEWS_KEYWORDS = {
    "tin",
    "tom tat",
    "diem tin",
    "ban tin",
    "nong",
    "hot",
    "hom nay",
}
COMMODITY_KEYWORDS = {"vang", "gold", "xang", "dau", "oil", "gasoline", "ty gia", "usd", "vnd", "sjc", "petrolimex"}


def _strip_accents(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text)
    return "".join(char for char in normalized if not unicodedata.combining(char))


def _normalize_query(text: str) -> str:
    value = _strip_accents(text)
    value = re.sub(r"\s+", " ", value).strip()
    value = re.sub(r"\b(gia|bao nhieu|price|mua|ban)\b", "", value, flags=re.I)
    return re.sub(r"\s+", " ", value).strip()


def _domain_label(url: str) -> str:
    host = urlparse(url).netloc.lower().replace("www.", "")
    for item in config.RETAIL_SEARCH_SITES:
        if item["domain"] in host:
            return item["label"]
    return host or "Nguồn web"


def _extract_price_from_text(text: str) -> dict[str, object] | None:
    if not text:
        return None

    patterns = [
        r"(?P<value>\d{1,3}(?:[.,]\d{3})+|\d+(?:[.,]\d+)?)\s*(?P<unit>triệu|trieu|nghìn|nghin|k|đ|đồng|dong|vnđ|vnd|usd)",
        r"(?P<value>\d+(?:[.,]\d+)?)\s*(?P<unit>triệu|trieu|k|usd)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.I)
        if not match:
            continue
        raw_value = match.group("value")
        unit = match.group("unit").lower()
        normalized = raw_value.replace(" ", "")
        context_start = max(0, match.start() - 40)
        context = _strip_accents(text[context_start:match.start()]).lower()
        if any(term in context for term in ("giam", "khuyen mai", "voucher", "deal", "uu dai", "tra gop")):
            if unit in {"triệu", "trieu", "nghìn", "nghin", "k"}:
                continue
        if unit in {"triệu", "trieu"}:
            try:
                cleaned = normalized.replace(".", "").replace(",", ".")
                value = float(cleaned) if cleaned else 0
            except ValueError:
                continue
            return {"value": value * 1_000_000, "currency": "VND", "raw": match.group(0)}
        if unit in {"nghìn", "nghin", "k"}:
            try:
                cleaned = normalized.replace(".", "").replace(",", ".")
                value = float(cleaned) if cleaned else 0
            except ValueError:
                continue
            return {"value": value * 1_000, "currency": "VND", "raw": match.group(0)}
        if unit in {"usd"}:
            try:
                cleaned = normalized.replace(".", "").replace(",", ".")
                value = float(cleaned) if cleaned else 0
            except ValueError:
                continue
            return {"value": value, "currency": "USD", "raw": match.group(0)}
        try:
            value = float(normalized.replace(".", "").replace(",", "."))
        except ValueError:
            continue
        return {"value": value, "currency": "VND", "raw": match.group(0)}
    return None


def _format_price(value: float | None, currency: str | None) -> str:
    if value is None:
        return ""
    if currency == "USD":
        return f"{value:,.2f} USD"
    return f"{value:,.0f} đ".replace(",", ".")


def _is_plausible_price(value: float | None, currency: str | None) -> bool:
    if value is None:
        return False
    if currency == "USD":
        return value >= 1
    return value >= 10_000


def _result_score(url: str, title: str, price: float | None, currency: str | None) -> tuple[int, float]:
    score = 0
    url_lower = url.lower()
    title_lower = title.lower()

    if any(token in url_lower for token in ("dtdd", "dien-thoai", "san-pham", "/product", "/p/")):
        score += 4
    if any(token in url_lower for token in ("tin-tuc", "blog", "sforum", "review", "news", "/tin-tuc/", "/sforum/")):
        score -= 3
    if any(token in title_lower for token in ("giá", "gia", "price", "chính hãng", "chinh hang", "mới", "moi")):
        score += 1
    if _is_plausible_price(price, currency):
        score += 3
    return score, float(price or 0)


def _walk_jsonld(obj, prices: list[dict[str, object]]) -> None:
    if isinstance(obj, dict):
        for key, value in obj.items():
            key_lower = str(key).lower()
            if key_lower in {"price", "lowprice", "highprice"}:
                try:
                    numeric = float(str(value).replace(".", "").replace(",", "."))
                    prices.append({"value": numeric, "currency": "VND", "raw": str(value)})
                except Exception:
                    pass
            elif key_lower == "pricecurrency" and prices:
                prices[-1]["currency"] = str(value)
            _walk_jsonld(value, prices)
    elif isinstance(obj, list):
        for item in obj:
            _walk_jsonld(item, prices)


def _extract_price_from_page(url: str) -> dict[str, object] | None:
    try:
        response = requests.get(url, headers=USER_AGENT, timeout=15)
        response.raise_for_status()
    except Exception:
        return None

    soup = BeautifulSoup(response.text, "html.parser")
    candidates = [
        ("meta", {"property": "product:price:amount"}, "content"),
        ("meta", {"property": "og:price:amount"}, "content"),
        ("meta", {"name": "price"}, "content"),
        ("meta", {"itemprop": "price"}, "content"),
    ]
    for tag_name, attrs, attr_name in candidates:
        tag = soup.find(tag_name, attrs=attrs)
        if not tag:
            continue
        raw_value = tag.get(attr_name)
        if not raw_value:
            continue
        try:
            numeric = float(str(raw_value).replace(".", "").replace(",", "."))
            return {"value": numeric, "currency": "VND", "raw": str(raw_value)}
        except Exception:
            pass

    jsonld_prices: list[dict[str, object]] = []
    for script in soup.find_all("script", type="application/ld+json"):
        text = script.get_text(strip=True)
        if not text or "price" not in text.lower():
            continue
        try:
            data = json.loads(text)
        except Exception:
            continue
        _walk_jsonld(data, jsonld_prices)
    if jsonld_prices:
        price = jsonld_prices[-1]
        currency = str(price.get("currency") or "VND")
        return {"value": float(price["value"]), "currency": currency, "raw": str(price.get("raw", ""))}

    page_text = soup.get_text(" ", strip=True)
    return _extract_price_from_text(page_text)


def _rank_price_hint(result: dict[str, object]) -> tuple[int, float]:
    price = result.get("price")
    return (0 if price else 1, float(price or 0))


def _search_ddgs(query: str, max_results: int = 5) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    with DDGS() as ddgs:
        for row in ddgs.text(query, max_results=max_results):
            rows.append(
                {
                    "title": row.get("title") or "",
                    "url": row.get("href") or row.get("url") or "",
                    "snippet": row.get("body") or row.get("snippet") or "",
                }
            )
    return rows


def detect_intent(question: str) -> dict[str, str]:
    text = _strip_accents(question).lower()
    if any(keyword in text for keyword in COMMODITY_KEYWORDS):
        return {"intent": "commodity", "topic": ""}
    if any(keyword in text for keyword in NEWS_KEYWORDS):
        topic = "all"
        if any(_strip_accents(alias).lower() in text for alias in config.NEWS_TOPIC_ALIASES["cong_nghe"]):
            topic = "cong_nghe"
        elif any(_strip_accents(alias).lower() in text for alias in config.NEWS_TOPIC_ALIASES["kinh_te"]):
            topic = "kinh_te"
        elif any(_strip_accents(alias).lower() in text for alias in config.NEWS_TOPIC_ALIASES["the_gioi"]):
            topic = "the_gioi"
        elif any(_strip_accents(alias).lower() in text for alias in config.NEWS_TOPIC_ALIASES["the_thao"]):
            topic = "the_thao"
        elif any(_strip_accents(alias).lower() in text for alias in config.NEWS_TOPIC_ALIASES["thoi_su"]):
            topic = "thoi_su"
        return {"intent": "news", "topic": topic}
    if any(keyword in text for keyword in PRICE_KEYWORDS):
        return {"intent": "product", "topic": ""}
    return {"intent": "general", "topic": ""}


def search_product_prices(question: str) -> dict[str, object]:
    cache_key = f"product-search:{question.lower().strip()}"
    cached = CACHE.get(cache_key)
    if cached:
        return cached

    product_query = _normalize_query(question)
    search_queries = [product_query or question.strip()]
    for site in config.RETAIL_SEARCH_SITES:
        search_queries.append(f"site:{site['domain']} {product_query or question.strip()}")

    rows: list[dict[str, object]] = []
    seen_urls: set[str] = set()
    for query in search_queries:
        try:
            results = _search_ddgs(query, max_results=config.PRODUCT_SEARCH_MAX_RESULTS)
        except Exception:
            continue
        for result in results:
            url = str(result.get("url") or "")
            if not url or url in seen_urls:
                continue
            host = urlparse(url).netloc.lower().replace("www.", "")
            if not any(domain in host for domain in PRICE_DOMAIN_ALLOWLIST):
                continue
            seen_urls.add(url)
            combined_text = f"{result.get('title', '')} {result.get('snippet', '')}"
            price_hint = _extract_price_from_page(url)
            if price_hint is None:
                price_hint = _extract_price_from_text(combined_text)
            if price_hint and not _is_plausible_price(price_hint.get("value"), price_hint.get("currency")):
                price_hint = None
            score, _ = _result_score(
                url,
                str(result.get("title", "")),
                price_hint.get("value") if price_hint else None,
                price_hint.get("currency") if price_hint else None,
            )
            rows.append(
                {
                    "title": result.get("title", ""),
                    "url": url,
                    "domain": _domain_label(url),
                    "snippet": result.get("snippet", ""),
                    "price": price_hint.get("value") if price_hint else None,
                    "currency": price_hint.get("currency") if price_hint else None,
                    "price_raw": price_hint.get("raw") if price_hint else "",
                    "price_text": _format_price(
                        price_hint.get("value") if price_hint else None,
                        price_hint.get("currency") if price_hint else None,
                    ),
                    "score": score,
                }
            )
    rows.sort(key=lambda row: (-int(row.get("score") or 0), -float(row.get("price") or 0)))
    rows = rows[:8]

    payload = {
        "query": question,
        "normalized_query": product_query,
        "results": rows,
    }
    CACHE.set(cache_key, payload, config.SEARCH_REFRESH_SECONDS)
    return payload


def search_general_web(question: str) -> dict[str, object]:
    cache_key = f"general-search:{question.lower().strip()}"
    cached = CACHE.get(cache_key)
    if cached:
        return cached

    rows: list[dict[str, object]] = []
    try:
        for result in _search_ddgs(question, max_results=config.WEB_SEARCH_MAX_RESULTS):
            url = str(result.get("url") or "")
            combined_text = f"{result.get('title', '')} {result.get('snippet', '')}"
            price_hint = _extract_price_from_text(combined_text)
            rows.append(
                {
                    "title": result.get("title", ""),
                    "url": url,
                    "domain": _domain_label(url),
                    "snippet": result.get("snippet", ""),
                    "price": price_hint.get("value") if price_hint else None,
                    "currency": price_hint.get("currency") if price_hint else None,
                    "price_raw": price_hint.get("raw") if price_hint else "",
                    "price_text": _format_price(
                        price_hint.get("value") if price_hint else None,
                        price_hint.get("currency") if price_hint else None,
                    ),
                }
            )
    except Exception:
        rows = []

    payload = {
        "query": question,
        "results": rows,
    }
    CACHE.set(cache_key, payload, config.SEARCH_REFRESH_SECONDS)
    return payload


def summarize_search(question: str, results: list[dict[str, object]]) -> str:
    if not results:
        return "Chưa tìm được nguồn phù hợp."

    prompt = f"""
Hãy trả lời câu hỏi bằng tiếng Việt dựa trên dữ liệu tìm kiếm web sau.
Không bịa số liệu. Nếu có giá, nêu rõ đó là giá tham khảo từ nguồn nào.
Trả lời ngắn gọn, thực dụng, dễ đọc.

Câu hỏi: {question}

Dữ liệu:
{compact_json(results[:6], limit=4500)}
""".strip()
    text = generate_text(prompt, max_output_tokens=260)
    if text:
        return text

    # Fallback: concise product-style listing (no AI available).
    has_prices = any(r.get("price_text") for r in results[:5])
    if has_prices:
        lines = ["Giá tham khảo từ các nguồn:"]
        for result in results[:5]:
            price_text = result.get("price_text") or ""
            if not price_text:
                continue
            domain = result.get("domain") or "Nguồn"
            title = str(result.get("title") or "")
            # Shorten title to product name only.
            short_title = title[:60] + "..." if len(title) > 60 else title
            lines.append(f"• {short_title}")
            lines.append(f"  {price_text} — {domain}")
        if not any("•" in line for line in lines):
            lines.append("Chưa tìm được giá cụ thể.")
        return "\n".join(lines)

    lines = ["Kết quả tìm kiếm:"]
    for result in results[:4]:
        title = str(result.get("title") or result.get("domain") or "Nguồn")
        short_title = title[:70] + "..." if len(title) > 70 else title
        lines.append(f"• {short_title}")
    return "\n".join(lines)
