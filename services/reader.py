"""Article reader: extract main content from a news URL.

Uses BeautifulSoup heuristics to pull the article body text from Vietnamese
news sites. The approach is intentionally simple (no headless browser):

1. Fetch the page HTML.
2. Try common article selectors used by VN outlets.
3. Fall back to the largest ``<p>``-dense block.
4. Strip ads, nav, scripts, styles.
5. Return clean paragraphs as a list of strings.

Results are cached per URL for 1 hour so repeated reads are instant.
"""

from __future__ import annotations

import re
from typing import Any

import requests
from bs4 import BeautifulSoup, Tag

from .cache import TTLCache

CACHE = TTLCache(namespace="reader")
CACHE_TTL = 3600  # 1 hour
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept-Language": "vi,en;q=0.8",
}
TIMEOUT = 15

# CSS selectors commonly wrapping article body on major VN news sites.
# Ordered by specificity — first match wins.
ARTICLE_SELECTORS = [
    "article.fck_detail",           # VnExpress
    "div.fck_detail",               # VnExpress variant
    "div.detail-content",           # Thanh Nien
    "div.detail__content",          # Thanh Nien variant
    "div#main-detail-body",         # Tuoi Tre
    "div.singular-content",         # Tuoi Tre variant
    "div.e-body__content",          # Dan Tri
    "div.detail-content",           # Dan Tri variant
    "div.the-article-body",         # Zing News
    "div.article__body",            # Zing variant
    "div.article-content",          # Tien Phong, NLD
    "div.content-detail",           # NLD variant
    "div.detail_text_vov",          # VOV
    "div.cms-body",                 # Nhan Dan
    "article .post-content",        # generic WordPress
    "div[itemprop='articleBody']",   # schema.org
    "article",                      # last resort semantic tag
]

# Tags to strip before extracting text.
STRIP_TAGS = {"script", "style", "nav", "footer", "aside", "iframe", "form", "noscript"}
STRIP_CLASSES = {"ads", "adsbygoogle", "social", "share", "related", "comment", "banner"}


def _is_junk_element(tag: Tag) -> bool:
    if tag.name in STRIP_TAGS:
        return True
    classes = " ".join(tag.get("class") or []).lower()
    if any(junk in classes for junk in STRIP_CLASSES):
        return True
    tag_id = (tag.get("id") or "").lower()
    if any(junk in tag_id for junk in STRIP_CLASSES):
        return True
    return False


def _extract_paragraphs(container: Tag) -> list[str]:
    """Walk the container and collect meaningful text paragraphs."""

    # Collect junk elements first, then decompose outside the iterator
    # to avoid mutating the tree while traversing (BS4 4.13+ crashes).
    junk = [el for el in container.find_all(True) if isinstance(el, Tag) and _is_junk_element(el)]
    for el in junk:
        el.decompose()

    paragraphs: list[str] = []
    for element in container.find_all(["p", "h2", "h3", "h4", "blockquote", "li"]):
        text = element.get_text(" ", strip=True)
        text = re.sub(r"\s+", " ", text).strip()
        if len(text) < 15:
            continue
        if text.endswith("...") and len(text) < 40:
            continue
        paragraphs.append(text)
    return paragraphs


def _find_article_container(soup: BeautifulSoup) -> Tag | None:
    for selector in ARTICLE_SELECTORS:
        container = soup.select_one(selector)
        if container:
            return container
    return None


def _fallback_largest_block(soup: BeautifulSoup) -> Tag | None:
    """Find the div with the most <p> children as a last resort."""

    best: Tag | None = None
    best_count = 0
    for div in soup.find_all("div"):
        p_count = len(div.find_all("p", recursive=False))
        if p_count > best_count:
            best_count = p_count
            best = div
    return best if best_count >= 3 else None


def fetch_article(url: str) -> dict[str, Any]:
    """Fetch and extract article content from a URL.

    Returns a dict with:
    - ``url``: the original URL
    - ``title``: extracted page title
    - ``paragraphs``: list of text paragraphs (main content)
    - ``word_count``: approximate word count
    - ``error``: error message if extraction failed, else None
    """

    if not url:
        return {"url": "", "title": "", "paragraphs": [], "word_count": 0, "error": "empty_url"}

    cached = CACHE.get(f"article:{url}")
    if cached:
        return cached

    try:
        response = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        response.raise_for_status()
    except Exception as exc:
        return {"url": url, "title": "", "paragraphs": [], "word_count": 0, "error": str(exc)}

    soup = BeautifulSoup(response.text, "html.parser")

    # Extract title from <title> or <h1>.
    title_tag = soup.find("h1") or soup.find("title")
    title = title_tag.get_text(" ", strip=True) if title_tag else ""
    title = re.sub(r"\s+", " ", title).strip()
    # Strip site name suffix like " - VnExpress"
    title = re.sub(r"\s*[-|–]\s*(VnExpress|Thanh Niên|Tuổi Trẻ|Dân Trí|Zing|Tiền Phong|NLD|VOV|BBC).*$", "", title, flags=re.I)

    container = _find_article_container(soup) or _fallback_largest_block(soup)
    if not container:
        return {"url": url, "title": title, "paragraphs": [], "word_count": 0, "error": "no_content"}

    paragraphs = _extract_paragraphs(container)
    if not paragraphs:
        return {"url": url, "title": title, "paragraphs": [], "word_count": 0, "error": "empty_content"}

    word_count = sum(len(p.split()) for p in paragraphs)

    result = {
        "url": url,
        "title": title,
        "paragraphs": paragraphs,
        "word_count": word_count,
        "error": None,
    }
    CACHE.set(f"article:{url}", result, CACHE_TTL)
    return result
