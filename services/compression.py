"""Dependency-free gzip compression for Flask responses.

We avoid pulling in ``flask-compress`` to keep the deploy image small. This
``after_request`` hook gzips text-ish responses (JSON, JS, CSS, HTML, SVG)
when the client advertises gzip support and the body is large enough to be
worth it. Small bodies are left alone since the gzip header overhead would
negate the saving.
"""

from __future__ import annotations

import gzip

from flask import Flask, request

# Don't bother compressing tiny payloads — the ~20-byte gzip overhead plus CPU
# cost isn't worth it below this threshold.
_MIN_SIZE = 1024

_COMPRESSIBLE = (
    "application/json",
    "application/javascript",
    "application/manifest+json",
    "text/html",
    "text/css",
    "text/plain",
    "image/svg+xml",
)


def _should_compress(content_type: str) -> bool:
    if not content_type:
        return False
    base = content_type.split(";", 1)[0].strip().lower()
    return base in _COMPRESSIBLE


def init_compression(app: Flask) -> None:
    """Register the gzip ``after_request`` hook on ``app``."""

    @app.after_request
    def _gzip(response):
        # Respect clients that can't handle gzip.
        accept = request.headers.get("Accept-Encoding", "")
        if "gzip" not in accept.lower():
            return response

        # Already encoded — leave it alone.
        if response.headers.get("Content-Encoding"):
            return response
        if not _should_compress(response.headers.get("Content-Type", "")):
            return response

        # Static files are sent with ``direct_passthrough`` (sendfile); flip it
        # off so we can read and compress the body.
        if response.direct_passthrough:
            response.direct_passthrough = False

        data = response.get_data()
        if len(data) < _MIN_SIZE:
            return response

        compressed = gzip.compress(data, compresslevel=6)
        # Guard against pathological cases where gzip grows the payload.
        if len(compressed) >= len(data):
            return response

        response.set_data(compressed)
        response.headers["Content-Encoding"] = "gzip"
        response.headers["Content-Length"] = str(len(compressed))
        response.headers.add("Vary", "Accept-Encoding")
        return response
