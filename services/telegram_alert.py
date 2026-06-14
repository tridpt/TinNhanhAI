"""Background watcher that pushes news matching keywords to Telegram.

Configuration is environment-driven so the feature is opt-in:
- ``TELEGRAM_BOT_TOKEN``: bot token from @BotFather
- ``TELEGRAM_CHAT_ID``: chat or channel id to receive alerts
- ``TELEGRAM_KEYWORDS``: comma-separated list of keywords to watch
- ``TELEGRAM_POLL_SECONDS``: how often to scan (default 600s)

The watcher tracks article URLs in a small JSON state file under
``state/telegram_seen.json`` so the same article is never sent twice.
"""

from __future__ import annotations

import json
import os
import threading
import time
import unicodedata
from collections.abc import Iterable
from pathlib import Path

import requests

import config

from .news import _collect_topic_items  # type: ignore[attr-defined]

STATE_DIR = Path(__file__).resolve().parent.parent / "state"
STATE_FILE = STATE_DIR / "telegram_seen.json"
MAX_REMEMBERED = 500


def _strip_accents(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text)
    return "".join(char for char in normalized if not unicodedata.combining(char)).lower()


def _split_keywords(raw: str) -> list[str]:
    return [item.strip() for item in raw.split(",") if item.strip()]


def _load_seen() -> set[str]:
    if not STATE_FILE.exists():
        return set()
    try:
        data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return set()
    if isinstance(data, list):
        return set(str(item) for item in data)
    return set()


def _save_seen(seen: Iterable[str]) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    items = list(seen)[-MAX_REMEMBERED:]
    STATE_FILE.write_text(json.dumps(items, ensure_ascii=False), encoding="utf-8")


def _send_message(token: str, chat_id: str, text: str) -> bool:
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        response = requests.post(
            url,
            json={
                "chat_id": chat_id,
                "text": text,
                "parse_mode": "HTML",
                "disable_web_page_preview": False,
            },
            timeout=15,
        )
        response.raise_for_status()
        return True
    except Exception:
        return False


def _matches_any(text: str, keywords: list[str]) -> str | None:
    haystack = _strip_accents(text)
    for keyword in keywords:
        if _strip_accents(keyword) in haystack:
            return keyword
    return None


def scan_once(*, dry_run: bool = False) -> list[dict]:
    """Run a single scan cycle. Returns the list of items that matched."""

    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    raw_keywords = os.getenv("TELEGRAM_KEYWORDS", "").strip()

    if not (token and chat_id and raw_keywords):
        return []

    keywords = _split_keywords(raw_keywords)
    if not keywords:
        return []

    seen = _load_seen()
    matched: list[dict] = []

    for topic_key in config.NEWS_TOPIC_ORDER:
        if topic_key == "all":
            continue
        items = _collect_topic_items(topic_key)
        for item in items:
            url = item.get("url") or ""
            if not url or url in seen:
                continue
            blob = f"{item.get('title', '')} {item.get('summary', '')}"
            hit = _matches_any(blob, keywords)
            if not hit:
                continue
            matched.append({**item, "_keyword": hit})
            seen.add(url)
            if not dry_run:
                message = (
                    f"<b>[{hit}]</b> {item.get('title', '')}\n"
                    f"{item.get('source', '')} · {item.get('published_label', '')}\n"
                    f"{url}"
                )
                _send_message(token, chat_id, message)

    if matched and not dry_run:
        _save_seen(seen)
    return matched


def run_forever() -> None:
    interval = max(60, int(os.getenv("TELEGRAM_POLL_SECONDS", "600")))
    print(f"[telegram] watcher started, interval={interval}s")
    while True:
        try:
            hits = scan_once()
            _record_scan(sent=len(hits))
            if hits:
                print(f"[telegram] sent {len(hits)} alert(s)")
        except Exception as exc:  # pragma: no cover - defensive
            _record_scan(error=str(exc))
            print(f"[telegram] scan failed: {exc}")
        time.sleep(interval)


_started = False
_lock = threading.Lock()
_status: dict[str, object] = {
    "running": False,
    "last_scan_ts": None,
    "last_sent": 0,
    "last_error": None,
}


def _record_scan(*, sent: int = 0, error: str | None = None) -> None:
    with _lock:
        _status["last_scan_ts"] = time.time()
        if error is None:
            _status["last_sent"] = sent
            _status["last_error"] = None
        else:
            _status["last_error"] = error


def watcher_status() -> dict[str, object]:
    """Snapshot of the watcher's health for the /api/health endpoint."""

    with _lock:
        return dict(_status)


def start_in_background() -> bool:
    """Spawn the watcher thread once if Telegram credentials are present."""

    global _started
    with _lock:
        if _started:
            return True
        if not (
            os.getenv("TELEGRAM_BOT_TOKEN")
            and os.getenv("TELEGRAM_CHAT_ID")
            and os.getenv("TELEGRAM_KEYWORDS")
        ):
            return False
        thread = threading.Thread(target=run_forever, name="telegram-watcher", daemon=True)
        thread.start()
        _started = True
        _status["running"] = True
        return True


if __name__ == "__main__":
    hits = scan_once()
    print(f"matched: {len(hits)}")
    for hit in hits:
        print(f"- [{hit['_keyword']}] {hit.get('title')} :: {hit.get('url')}")
