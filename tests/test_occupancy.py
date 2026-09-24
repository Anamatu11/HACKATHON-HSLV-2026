"""Módulo de ocupación hospitalaria: filtros por servicio/subservicio/especialidad, diario/mensual."""
import pytest

from app import occupancy
from tests.conftest import requires_db

pytestmark = requires_db


def test_filters_list_services_with_subservices():
    f = occupancy.get_filters()
    services = {s["service"]: s for s in f["services"]}
    assert len(services) == 9
    uci_subs = {s["label"] for s in services["UCI"]["sub_services"]}
    assert uci_subs == {"UCI Adultos", "UCI Neonatal", "UCI Pediátrica"}
    assert "MEDICINA INTERNA" in {s["value"] for s in f["specialties"]}
    assert f["reference_date"] == "2026-09-21" and f["reliable_from"] == "2026-06-01"


def test_whole_hospital_daily_ends_today():
    r = occupancy.get_occupancy()
    assert r["labels"][-1] == "2026-09-21"
    assert r["scope"]["label"] == "Todo el hospital"
    assert len(r["occupied"]) == len(r["labels"]) == len(r["physical_pct"])


def test_uci_history_uses_billed_stays():
    r = occupancy.get_occupancy(service="UCI", granularity="monthly", start="2026-06-01")
    by_month = dict(zip(r["labels"], r["occupied"]))
    assert 18 <= by_month["2026-06"] <= 25          # ~21,6 camas/día (antes el censo daba ~3)
    assert any("estancias facturadas" in n for n in r["notes"])


def test_recent_undercount_window_is_flagged_for_critical_units():
    assert occupancy.get_occupancy(service="UCI")["incomplete_from"] == "2026-09-07"
    assert occupancy.get_occupancy(service="Pediatría")["incomplete_from"] is None
    assert occupancy.get_occupancy(specialty="MEDICINA INTERNA")["incomplete_from"] is None


def test_uci_neonatal_today_is_full():
    r = occupancy.get_occupancy(service="UCI", sub_service="UNIDAD DE CUIDADO INTENSIVO NEONATAL",
                                start="2026-09-21", end="2026-09-21")
    assert r["occupied"] == [15] and r["physical_pct"] == [100.0]
    assert r["scope"]["label"] == "UCI · UCI Neonatal"


def test_specialty_census_has_no_capacity():
    r = occupancy.get_occupancy(specialty="MEDICINA INTERNA", granularity="monthly")
    by_month = dict(zip(r["labels"], r["occupied"]))
    assert 95 <= by_month["2026-07"] <= 115
    assert r["capacity"] is None and all(v is None for v in r["physical_pct"])


def test_summary_and_comparison_table():
    r = occupancy.get_occupancy(start="2026-06-01")
    s = r["summary"]
    assert s["max"] >= s["avg"] >= s["min"] and s["max_date"]
    rows = {row["service"]: row for row in r["by_service"]}
    assert rows["Pediatría"]["avg_physical_pct"] > 100          # sobreocupación sostenida
    assert r["monthly_matrix"]["months"][0] == "2026-06"


def test_early_period_warning():
    r = occupancy.get_occupancy(start="2026-05-01", end="2026-05-31")
    assert any("mayo" in n.lower() for n in r["notes"])


@pytest.mark.parametrize("kwargs", [
    {"service": "Cardiología"},
    {"service": "UCI", "sub_service": "PEDIATRIA"},
    {"specialty": "NO EXISTE"},
    {"granularity": "anual"},
    {"start": "2026-13-01"},
])
def test_invalid_filters_raise_value_error(kwargs):
    with pytest.raises(ValueError):
        occupancy.get_occupancy(**kwargs)
