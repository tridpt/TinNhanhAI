"""Tests for the price-alert store, watcher logic, and REST endpoints."""

from __future__ import annotations

# --- Store -------------------------------------------------------------------


def test_add_and_list_alert(isolated_alerts):
    a = isolated_alerts.add_alert("crypto_btcusdt", "above", 100000, label="Bitcoin", unit="USD")
    assert a is not None
    rows = isolated_alerts.list_alerts()
    assert len(rows) == 1
    assert rows[0]["item_key"] == "crypto_btcusdt"
    assert rows[0]["direction"] == "above"
    assert rows[0]["active"] == 1


def test_add_alert_rejects_bad_input(isolated_alerts):
    assert isolated_alerts.add_alert("", "above", 1) is None
    assert isolated_alerts.add_alert("k", "sideways", 1) is None
    assert isolated_alerts.add_alert("k", "above", "not-a-number") is None


def test_delete_alert(isolated_alerts):
    a = isolated_alerts.add_alert("gold", "below", 90, label="Vàng")
    assert isolated_alerts.delete_alert(a["id"]) is True
    assert isolated_alerts.delete_alert(a["id"]) is False
    assert isolated_alerts.list_alerts() == []


def test_mark_triggered_deactivates(isolated_alerts):
    a = isolated_alerts.add_alert("gold", "above", 100, label="Vàng")
    isolated_alerts.mark_triggered(a["id"], 105.0)
    active = isolated_alerts.list_alerts(active_only=True)
    assert active == []
    all_rows = isolated_alerts.list_alerts()
    assert all_rows[0]["triggered_price"] == 105.0


def test_is_crossed():
    from services.alerts import is_crossed

    assert is_crossed("above", 120, 100) is True
    assert is_crossed("above", 90, 100) is False
    assert is_crossed("below", 90, 100) is True
    assert is_crossed("below", 120, 100) is False
    assert is_crossed("bogus", 1, 1) is False


# --- Watcher logic -----------------------------------------------------------


def test_scan_once_triggers_and_deactivates(isolated_alerts, monkeypatch):
    from services import price_alert

    isolated_alerts.add_alert("crypto_btcusdt", "above", 100000, label="Bitcoin", unit="USD")
    isolated_alerts.add_alert("crypto_ethusdt", "below", 1000, label="Ether", unit="USD")

    monkeypatch.setattr(
        price_alert,
        "collect_current_prices",
        lambda: {
            "crypto_btcusdt": {"price": 120000.0, "label": "Bitcoin", "unit": "USD"},
            "crypto_ethusdt": {"price": 2000.0, "label": "Ether", "unit": "USD"},
        },
    )
    # Don't actually hit Telegram.
    monkeypatch.setattr(price_alert, "_send_telegram", lambda text: True)

    triggered = price_alert.scan_once()
    assert len(triggered) == 1
    assert triggered[0]["item_key"] == "crypto_btcusdt"
    # The BTC alert is now inactive; ETH still waiting.
    assert len(isolated_alerts.list_alerts(active_only=True)) == 1


# --- Endpoints ---------------------------------------------------------------


def test_alerts_crud_endpoints(flask_client):
    # Initially empty.
    assert flask_client.get("/api/alerts").get_json()["alerts"] == []

    # Create.
    res = flask_client.post("/api/alerts", json={
        "item_key": "gold", "label": "Vàng", "unit": "USD/oz",
        "direction": "above", "threshold": 3000,
    })
    assert res.status_code == 201
    alert_id = res.get_json()["id"]

    # List shows it.
    assert len(flask_client.get("/api/alerts").get_json()["alerts"]) == 1

    # Delete.
    assert flask_client.delete(f"/api/alerts/{alert_id}").status_code == 200
    assert flask_client.get("/api/alerts").get_json()["alerts"] == []


def test_alerts_create_rejects_invalid(flask_client):
    res = flask_client.post("/api/alerts", json={"item_key": "", "direction": "x", "threshold": 1})
    assert res.status_code == 400


def test_alerts_delete_missing(flask_client):
    assert flask_client.delete("/api/alerts/99999").status_code == 404
