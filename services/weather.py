"""Weather snippets for major Vietnamese cities via Open-Meteo (free, no auth)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import requests

import config

from .cache import TTLCache

LOCAL_TZ = timezone(timedelta(hours=7))
CACHE = TTLCache(namespace="weather")
HEADERS = {"User-Agent": "Mozilla/5.0 TinNhanhAI/1.0"}
TIMEOUT = 10

CITIES = [
    {"key": "hanoi", "label": "Hà Nội", "lat": 21.03, "lon": 105.85},
    {"key": "danang", "label": "Đà Nẵng", "lat": 16.05, "lon": 108.20},
    {"key": "hcm", "label": "TP HCM", "lat": 10.76, "lon": 106.66},
]

# WMO weather codes → human label + lucide icon.
# We don't need to map every code — bucket them into the common cases.
WEATHER_CODE_MAP = {
    0: ("Trời quang", "sun"),
    1: ("Phần lớn quang", "sun"),
    2: ("Có mây", "cloud"),
    3: ("Nhiều mây", "cloudy"),
    45: ("Sương mù", "cloud-fog"),
    48: ("Sương mù đóng băng", "cloud-fog"),
    51: ("Mưa phùn nhẹ", "cloud-drizzle"),
    53: ("Mưa phùn", "cloud-drizzle"),
    55: ("Mưa phùn nặng", "cloud-drizzle"),
    61: ("Mưa nhỏ", "cloud-rain"),
    63: ("Mưa", "cloud-rain"),
    65: ("Mưa to", "cloud-rain"),
    71: ("Tuyết nhẹ", "cloud-snow"),
    73: ("Tuyết", "cloud-snow"),
    75: ("Tuyết dày", "cloud-snow"),
    80: ("Mưa rào nhẹ", "cloud-drizzle"),
    81: ("Mưa rào", "cloud-rain"),
    82: ("Mưa rào lớn", "cloud-rain-wind"),
    95: ("Dông", "cloud-lightning"),
    96: ("Dông + mưa đá", "cloud-lightning"),
    99: ("Dông mạnh", "cloud-lightning"),
}


def _describe_code(code: int | None) -> tuple[str, str]:
    if code is None:
        return ("Chưa rõ", "cloud")
    return WEATHER_CODE_MAP.get(int(code), ("Thời tiết", "cloud"))


def fetch_weather() -> list[dict[str, Any]]:
    cards: list[dict[str, Any]] = []
    for city in CITIES:
        try:
            response = requests.get(
                "https://api.open-meteo.com/v1/forecast",
                params={
                    "latitude": city["lat"],
                    "longitude": city["lon"],
                    "current": (
                        "temperature_2m,relative_humidity_2m,"
                        "weather_code,wind_speed_10m,apparent_temperature"
                    ),
                    "timezone": "Asia/Ho_Chi_Minh",
                },
                headers=HEADERS,
                timeout=TIMEOUT,
            )
            response.raise_for_status()
            data = response.json()
        except Exception:
            continue

        current = data.get("current") or {}
        if not current:
            continue
        code = current.get("weather_code")
        label, icon = _describe_code(code)

        temp = current.get("temperature_2m")
        feels = current.get("apparent_temperature")
        humidity = current.get("relative_humidity_2m")
        wind = current.get("wind_speed_10m")

        cards.append(
            {
                "key": f"weather_{city['key']}",
                "city": city["label"],
                "label": label,
                "icon": icon,
                "temperature": temp,
                "feels_like": feels,
                "humidity": humidity,
                "wind_speed": wind,
                "weather_code": code,
                "updated_at": current.get("time", ""),
                "temperature_text": f"{temp:.0f}°C" if temp is not None else "",
                "feels_like_text": f"{feels:.0f}°C" if feels is not None else "",
                "humidity_text": f"{humidity}%" if humidity is not None else "",
                "wind_text": f"{wind:.1f} km/h" if wind is not None else "",
                "source_url": f"https://open-meteo.com/en/docs#latitude={city['lat']}&longitude={city['lon']}",
            }
        )
    return cards


def get_weather_payload(*, force: bool = False) -> dict[str, Any]:
    cache_key = "weather"
    if not force:
        cached = CACHE.get(cache_key)
        if cached:
            return cached

    cards = fetch_weather()
    payload = {
        "generated_at": datetime.now(LOCAL_TZ).isoformat(),
        "cities": cards,
    }
    CACHE.set(cache_key, payload, config.PRICE_REFRESH_SECONDS)
    return payload
