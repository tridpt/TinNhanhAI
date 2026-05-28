"""Tests for VND number parsing and VN gold provider scaling."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from services.vn_prices import _parse_vn_number


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("26143.00", 26143.0),       # US-style decimal (Vietcombank API)
        ("26.143,50", 26143.50),     # VN style: dot=thousand, comma=decimal
        ("1.234.567", 1234567.0),    # plain VN thousand grouping
        ("75013146", 75013146.0),    # plain integer
        ("", None),
        ("abc", None),
        ("--", None),
    ],
)
def test_parse_vn_number(raw, expected):
    assert _parse_vn_number(raw) == expected


def test_parse_vn_number_treats_single_comma_as_decimal():
    """A lone comma is interpreted as the decimal separator (VN convention).

    SJC's HTML field "157,700" uses the comma as a thousand separator, but
    the SJC fetcher consumes the numeric ``BuyValue`` field instead, so this
    edge case never bites the dashboard in practice.
    """

    assert _parse_vn_number("157,700") == 157.7


# --- VN gold provider scaling ----------------------------------------------------------


def _mock_response(payload, *, status_code=200):
    response = MagicMock()
    response.status_code = status_code
    response.raise_for_status = MagicMock()
    response.json = MagicMock(return_value=payload)
    return response


def test_pnj_scales_thousand_per_chi_to_vnd_per_luong(monkeypatch):
    """PNJ returns ``giamua=15770`` (nghìn đồng/chỉ) → 157,700,000 VND/lượng."""

    from services import vn_gold

    fake_payload = {
        "data": [
            {"masp": "SJC", "tensp": "Vàng SJC", "giamua": 15770, "giaban": 16070},
            {"masp": "N24K", "tensp": "Nhẫn Trơn PNJ", "giamua": 15700, "giaban": 16000},
            {"masp": "UNKNOWN", "tensp": "Bỏ qua", "giamua": 100, "giaban": 110},
        ]
    }
    monkeypatch.setattr(vn_gold.requests, "get", lambda *a, **kw: _mock_response(fake_payload))

    cards = vn_gold.fetch_pnj()
    sjc = next(card for card in cards if card["key"] == "vn_gold_pnj_sjc")

    assert sjc["buy"] == 157_700_000
    assert sjc["sell"] == 160_700_000
    assert sjc["unit"] == "VND/lượng"
    assert sjc["provider"] == "PNJ"
    # Unknown product codes are filtered out so the dashboard stays compact.
    assert all("unknown" not in card["key"] for card in cards)


def test_btmc_scales_dong_per_chi_to_vnd_per_luong(monkeypatch):
    """BTMC raw 15,770,000 đồng/chỉ → 157,700,000 VND/lượng."""

    from services import vn_gold

    fake_payload = {
        "DataList": {
            "Data": [
                {
                    "@row": "1",
                    "@n_1": "VÀNG MIẾNG SJC (Vàng SJC)",
                    "@pb_1": "15770000",
                    "@ps_1": "16070000",
                },
                {
                    "@row": "2",
                    "@n_2": "BẠC MIẾNG PHÚ QUÝ Ag 999",
                    "@pb_2": "75013146",
                    "@ps_2": "77333140",
                },
            ]
        }
    }
    monkeypatch.setattr(vn_gold.requests, "get", lambda *a, **kw: _mock_response(fake_payload))

    cards = vn_gold.fetch_btmc()
    sjc = next(card for card in cards if "sjc" in card["key"])

    assert sjc["buy"] == 157_700_000
    assert sjc["sell"] == 160_700_000
    # Silver entries should be filtered out even if a regex pattern grazes them.
    assert all("PHÚ QUÝ" not in card["label"] for card in cards)


def test_pnj_returns_empty_on_network_error(monkeypatch):
    from services import vn_gold

    def boom(*args, **kwargs):
        raise vn_gold.requests.RequestException("nope")

    monkeypatch.setattr(vn_gold.requests, "get", boom)
    assert vn_gold.fetch_pnj() == []


def test_aggregator_dedupes_by_key(monkeypatch):
    from services import vn_gold

    monkeypatch.setattr(vn_gold, "fetch_sjc", lambda: [
        {"key": "shared", "label": "A", "provider": "SJC", "buy": 1, "sell": 2,
         "icon": "x", "unit": "VND/lượng", "source_url": "", "updated_label": ""}
    ])
    monkeypatch.setattr(vn_gold, "fetch_pnj", lambda: [
        {"key": "shared", "label": "B", "provider": "PNJ", "buy": 3, "sell": 4,
         "icon": "x", "unit": "VND/lượng", "source_url": "", "updated_label": ""},
        {"key": "unique", "label": "C", "provider": "PNJ", "buy": 5, "sell": 6,
         "icon": "x", "unit": "VND/lượng", "source_url": "", "updated_label": ""},
    ])
    monkeypatch.setattr(vn_gold, "fetch_btmc", lambda: [])

    cards = vn_gold.fetch_all_vn_gold()
    keys = [c["key"] for c in cards]

    assert keys == ["shared", "unique"]
    # First fetcher (SJC) wins for duplicate keys.
    assert cards[0]["provider"] == "SJC"
