from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent


def _load_env_file() -> None:
    env_path = BASE_DIR / ".env"
    if not env_path.exists():
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


_load_env_file()


APP_NAME = os.getenv("APP_NAME", "TinNhanh AI")
HOST = os.getenv("HOST", "127.0.0.1")
PORT = int(os.getenv("PORT", "5055"))
DEBUG = os.getenv("DEBUG", "1").lower() not in {"0", "false", "no"}

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip()

ASK_RATE_LIMIT_PER_MINUTE = int(os.getenv("ASK_RATE_LIMIT_PER_MINUTE", "20"))

NEWS_REFRESH_SECONDS = int(os.getenv("NEWS_REFRESH_SECONDS", "900"))
PRICE_REFRESH_SECONDS = int(os.getenv("PRICE_REFRESH_SECONDS", "300"))
DASHBOARD_REFRESH_SECONDS = int(os.getenv("DASHBOARD_REFRESH_SECONDS", "600"))
SEARCH_REFRESH_SECONDS = int(os.getenv("SEARCH_REFRESH_SECONDS", "300"))

NEWS_TOPIC_ORDER = ["all", "thoi_su", "kinh_te", "cong_nghe", "the_gioi", "the_thao"]

NEWS_TOPIC_META = {
    "all": {
        "label": "Tổng hợp",
        "icon": "layout-grid",
    },
    "thoi_su": {
        "label": "Thời sự",
        "icon": "newspaper",
    },
    "kinh_te": {
        "label": "Kinh tế",
        "icon": "chart-column",
    },
    "cong_nghe": {
        "label": "Công nghệ",
        "icon": "cpu",
    },
    "the_gioi": {
        "label": "Thế giới",
        "icon": "globe",
    },
    "the_thao": {
        "label": "Thể thao",
        "icon": "trophy",
    },
}

NEWS_TOPIC_SOURCES = {
    "thoi_su": [
        {"name": "VnExpress", "url": "https://vnexpress.net/rss/thoi-su.rss"},
        {"name": "Thanh Niên", "url": "https://thanhnien.vn/rss/thoi-su.rss"},
    ],
    "kinh_te": [
        {"name": "VnExpress", "url": "https://vnexpress.net/rss/kinh-doanh.rss"},
        {"name": "Thanh Niên", "url": "https://thanhnien.vn/rss/kinh-te.rss"},
    ],
    "cong_nghe": [
        {"name": "VnExpress", "url": "https://vnexpress.net/rss/khoa-hoc-cong-nghe.rss"},
        {"name": "Thanh Niên", "url": "https://thanhnien.vn/rss/cong-nghe.rss"},
    ],
    "the_gioi": [
        {"name": "VnExpress", "url": "https://vnexpress.net/rss/the-gioi.rss"},
        {"name": "Thanh Niên", "url": "https://thanhnien.vn/rss/the-gioi.rss"},
    ],
    "the_thao": [
        {"name": "VnExpress", "url": "https://vnexpress.net/rss/the-thao.rss"},
        {"name": "Thanh Niên", "url": "https://thanhnien.vn/rss/the-thao.rss"},
    ],
}

NEWS_TOPIC_ALIASES = {
    "thoi_su": ["thời sự", "thoi su", "chính trị", "xã hội", "tin nóng", "trong nước"],
    "kinh_te": ["kinh tế", "tài chính", "doanh nghiệp", "chứng khoán", "đầu tư", "giá cả"],
    "cong_nghe": ["công nghệ", "khoa học", "ai", "điện thoại", "laptop", "tech"],
    "the_gioi": ["thế giới", "quốc tế", "ngoài nước", "world"],
    "the_thao": ["thể thao", "bóng đá", "sports", "football", "olympic"],
}

PRICE_SPECS = [
    {
        "key": "gold",
        "label": "Vàng thế giới",
        "symbol": "GC=F",
        "unit": "USD/oz",
        "precision": 2,
        "icon": "crown",
    },
    {
        "key": "oil",
        "label": "Dầu thô WTI",
        "symbol": "CL=F",
        "unit": "USD/thùng",
        "precision": 2,
        "icon": "fuel",
    },
    {
        "key": "gasoline",
        "label": "Xăng RBOB",
        "symbol": "RB=F",
        "unit": "USD/gallon",
        "precision": 4,
        "icon": "car-front",
    },
]

RETAIL_SEARCH_SITES = [
    {"domain": "didongviet.vn", "label": "Di Động Việt"},
    {"domain": "thegioididong.com", "label": "Thế Giới Di Động"},
    {"domain": "cellphones.com.vn", "label": "CellphoneS"},
    {"domain": "fptshop.com.vn", "label": "FPT Shop"},
    {"domain": "viettelstore.vn", "label": "Viettel Store"},
    {"domain": "topzone.vn", "label": "TopZone"},
]

WEB_SEARCH_MAX_RESULTS = int(os.getenv("WEB_SEARCH_MAX_RESULTS", "6"))
PRODUCT_SEARCH_MAX_RESULTS = int(os.getenv("PRODUCT_SEARCH_MAX_RESULTS", "5"))

