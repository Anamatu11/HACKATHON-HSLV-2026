"""KPIs del dashboard contra las cifras validadas en hospital.db (reference_date 2026-09-21)."""
from app import kpis
from tests.conftest import requires_db

pytestmark = requires_db


def cards_by_id():
    return {c["id"]: c for c in kpis.get_kpis()["cards"]}


def test_response_shape():
    body = kpis.get_kpis()
    assert body["reference_date"] == "2026-09-21"
    assert {"occupancy_daily", "occupancy_by_service", "surgery", "admissions_by_service",
            "admissions_daily", "wait_by_triage", "top_medications", "low_medications",
            "top_specialties"} <= set(body["series"])
    assert body["medications_table"]


def test_card_values_match_demo():
    cards = cards_by_id()
    assert cards["uci_occupancy"]["value"] == 58.7
    assert cards["avg_wait_7d"]["value"] == 58.6
    assert cards["critical_stock"]["value"] == 35
    assert cards["surgery_performed"]["value"] == 85.9
    assert cards["admissions_month"]["value"] >= 1169 + 409 + 401   # al menos los 3 servicios principales


def test_hospital_occupancy_uses_physical_beds():
    card = cards_by_id()["hospital_occupancy"]
    assert card["value"] == 102.5          # 374 pacientes / 365 camas físicas
    assert card["status"] == "critical"


def test_every_card_has_status_and_detail():
    for card in kpis.get_kpis()["cards"]:
        assert card["status"] in {"ok", "warning", "critical"}
        assert card["detail"]


def test_occupancy_daily_is_a_30_day_line_series():
    series = kpis.get_kpis()["series"]["occupancy_daily"]
    assert len(series["labels"]) == 30 and series["labels"][-1] == "2026-09-21"
    assert {d["label"] for d in series["datasets"]} >= {"UCI", "Pediatría"}


def test_admissions_daily_has_moving_average():
    series = kpis.get_kpis()["series"]["admissions_daily"]
    assert len(series["data"]) == len(series["moving_avg_7d"]) == len(series["labels"])


def test_medications_table_has_no_personal_data():
    row = kpis.get_kpis()["medications_table"][0]
    assert set(row) == {"item_code", "item_name", "stock_units", "avg_daily_consumption",
                        "days_of_inventory", "expiry_date", "status"}


def test_admissions_table_has_no_personal_data():
    body = kpis.get_kpis()
    assert "admissions_table" in body
    assert len(body["admissions_table"]) > 0
    row = body["admissions_table"][0]
    # Garantiza que nunca se expongan datos personales
    assert {"patient_id", "patient_name", "document_type"} & set(row) == set()
    assert {"admission_at", "service", "sub_service", "sex", "age_group", "diagnosis_chapter"} <= set(row)

