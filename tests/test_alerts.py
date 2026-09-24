"""Alertas y recomendaciones con los datos reales (reference_date 2026-09-21)."""
from app import alerts
from tests.conftest import requires_db

pytestmark = requires_db

SEVERITY_ORDER = {"critical": 0, "warning": 1, "info": 2}


def test_alert_shape_and_order():
    items = alerts.get_alerts()
    assert items
    for a in items:
        assert set(a) >= {"type", "severity", "title", "detail", "action"}
    ranks = [SEVERITY_ORDER[a["severity"]] for a in items]
    assert ranks == sorted(ranks)


def test_critical_stock_alert_exists():
    stock = alerts.stock_alerts()
    assert any(a["severity"] == "critical" for a in stock)
    assert "NIFEDIPINO" in stock[0]["title"]


def test_pediatrics_overcrowding_is_flagged_with_reassignment_hint():
    occ = alerts.occupancy_alerts()
    pedia = next(a for a in occ if "Pediatría" in a["title"])
    assert pedia["severity"] == "critical"
    assert "reasign" in pedia["action"].lower()


def test_critical_subunit_alert_uci_neonatal_full():
    occ = alerts.occupancy_alerts()
    assert any("UCI Neonatal" in a["title"] and a["severity"] == "critical" for a in occ)


def test_triage2_wait_alert_includes_root_cause():
    wait = alerts.wait_time_alerts()
    t2 = next(a for a in wait if "triage 2" in a["title"].lower())
    assert "turno" in t2["detail"].lower()


def test_respiratory_forecast_alert():
    forecast = alerts.forecast_alerts()
    assert any("respiratori" in a["title"].lower() for a in forecast)


def test_surgery_alert_mentions_reprogramming():
    assert any("reprogram" in a["detail"].lower() for a in alerts.surgery_alerts())


def test_recommendations_for_stock_answer():
    recs = alerts.recommendations_for("medicamentos", ["item_name", "days_of_inventory"], [["X", 0.8]])
    assert recs and "X" in recs[0]


def test_recommendations_for_unknown_topic_is_empty():
    assert alerts.recommendations_for("hola", ["a"], [[1]]) == []
