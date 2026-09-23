"""
Las 4 preguntas de la demo DEBEN dar estas cifras (CLAUDE.md §1). Requiere data/hospital.db generado.

Si cambia el ETL, esta prueba avisa antes que el jurado.
"""
from pathlib import Path

import pytest

from app.agent.agent import answer_question
from app.agent.fallback import match_rule

pytestmark = pytest.mark.skipif(not Path("data/hospital.db").exists(),
                                reason="Falta data/hospital.db: correr el ETL")

DEMO = {
    "uci_occupancy_today": "¿Cuántas camas de UCI están ocupadas hoy?",
    "critical_stock": "¿Cuáles son los medicamentos con menos de 5 días de inventario?",
    "er_wait_last_week": "¿Cuál es el tiempo de espera promedio en urgencias en la última semana?",
    "admissions_by_service_this_month": "¿Qué servicio tiene más pacientes ingresados este mes?",
}


@pytest.mark.parametrize("rule_name,question", DEMO.items())
def test_demo_questions_match_a_rule(rule_name, question):
    rule = match_rule(question)
    assert rule is not None and rule.name == rule_name


def test_q1_uci_occupancy():
    r = answer_question(DEMO["uci_occupancy_today"])
    row = dict(zip(r["columns"], r["rows"][0]))
    assert (row["occupied_beds"], row["capacity_beds"], row["occupancy_pct"]) == (27, 46, 58.7)


def test_q2_critical_stock():
    assert len(answer_question(DEMO["critical_stock"])["rows"]) == 35


def test_q3_er_wait():
    r = answer_question(DEMO["er_wait_last_week"])
    total = sum(dict(zip(r["columns"], row))["attentions"] for row in r["rows"])
    assert total == 888


def test_q4_top_service():
    r = answer_question(DEMO["admissions_by_service_this_month"])
    assert r["rows"][0][:2] == ["Urgencias", 1169]
