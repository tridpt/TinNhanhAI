"""Capture README screenshots with Playwright.

Drives the running dev server (http://127.0.0.1:5055) in headless Chromium at
desktop and mobile viewports, then writes PNGs into ``docs/screenshots/``.

Usage (with the app already running):
    python -m playwright install chromium   # once
    python scripts/capture_screenshots.py
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE_URL = "http://127.0.0.1:5055"
OUT_DIR = Path(__file__).resolve().parent.parent / "docs" / "screenshots"


def _settle(page, seconds: float = 2.5) -> None:
    """Give the SPA time to fetch dashboard data and render charts."""
    page.wait_for_load_state("networkidle")
    time.sleep(seconds)


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch()

        # --- Desktop (light theme) ---
        desktop = browser.new_context(viewport={"width": 1280, "height": 900}, device_scale_factor=2)
        page = desktop.new_page()
        page.goto(BASE_URL, wait_until="domcontentloaded")
        _settle(page)
        page.screenshot(path=str(OUT_DIR / "dashboard-desktop.png"))
        print(f"wrote {OUT_DIR / 'dashboard-desktop.png'}")

        # --- Desktop (dark theme) ---
        page.evaluate(
            "document.documentElement.setAttribute('data-theme','dark');"
            "localStorage.setItem('tnai.theme','dark');"
        )
        time.sleep(1.0)
        page.screenshot(path=str(OUT_DIR / "dashboard-desktop-dark.png"))
        print(f"wrote {OUT_DIR / 'dashboard-desktop-dark.png'}")
        desktop.close()

        # --- Mobile (iPhone-ish viewport) ---
        mobile = browser.new_context(
            viewport={"width": 390, "height": 844},
            device_scale_factor=3,
            is_mobile=True,
            has_touch=True,
        )
        mpage = mobile.new_page()
        mpage.goto(BASE_URL, wait_until="domcontentloaded")
        _settle(mpage)
        mpage.screenshot(path=str(OUT_DIR / "dashboard-mobile.png"))
        print(f"wrote {OUT_DIR / 'dashboard-mobile.png'}")
        mobile.close()

        browser.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
