"""Lightweight structured logging for TinNhanh AI.

On Fly.io (and any aggregator) JSON lines are far easier to filter/query than
free-form ``print`` output. :func:`log_event` emits one JSON object per line
when ``LOG_JSON`` is truthy (default ON in production, i.e. when ``DEBUG`` is
off), and a readable ``[tag] message key=value`` line otherwise for local dev.

Usage::

    from services.logbook import log_event
    log_event("telegram", "sent alerts", count=3)
"""

from __future__ import annotations

import json
import os
import sys
import time
from typing import Any

import config


def _json_enabled() -> bool:
    raw = os.getenv("LOG_JSON", "").strip().lower()
    if raw in {"1", "true", "yes"}:
        return True
    if raw in {"0", "false", "no"}:
        return False
    # Default: structured logs in production (DEBUG off), plain text in dev.
    return not config.DEBUG


def log_event(tag: str, message: str, *, level: str = "info", **fields: Any) -> None:
    """Emit one log line. ``tag`` groups related events (e.g. ``"telegram"``)."""

    if _json_enabled():
        record: dict[str, Any] = {
            "ts": time.time(),
            "level": level,
            "tag": tag,
            "msg": message,
        }
        record.update(fields)
        try:
            line = json.dumps(record, ensure_ascii=False, default=str)
        except Exception:
            line = json.dumps({"ts": time.time(), "level": "error", "tag": "logbook",
                               "msg": "failed to serialise log record"})
        stream = sys.stderr if level in {"error", "warning"} else sys.stdout
        print(line, file=stream, flush=True)
    else:
        extra = " ".join(f"{k}={v}" for k, v in fields.items())
        suffix = f" {extra}" if extra else ""
        print(f"[{tag}] {message}{suffix}", flush=True)
