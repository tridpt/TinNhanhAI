"""Flask blueprints for TinNhanh AI.

Routes are split by concern so ``app.py`` stays a thin assembler:

- :mod:`routes.pages`   — static shell, manifest, service worker, icons, health
- :mod:`routes.news`    — dashboard + per-topic news feeds
- :mod:`routes.market`  — prices, crypto, stocks, forex, weather, history
- :mod:`routes.ai`      — ask / read / summarize (rate-limited AI endpoints)

Each module exposes a ``bp`` blueprint registered by :func:`register_blueprints`.
"""

from __future__ import annotations

from flask import Flask


def register_blueprints(app: Flask) -> None:
    from .ai import bp as ai_bp
    from .market import bp as market_bp
    from .news import bp as news_bp
    from .pages import bp as pages_bp

    app.register_blueprint(pages_bp)
    app.register_blueprint(news_bp)
    app.register_blueprint(market_bp)
    app.register_blueprint(ai_bp)


def _wants_force(request_args) -> bool:
    """Shared parser for the ``?force=`` query flag."""

    return request_args.get("force", "0").lower() in {"1", "true", "yes"}
