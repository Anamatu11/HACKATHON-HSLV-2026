"""Especificación del orquestador del agente (agent.py) con un LLM falso."""
import pytest

from app.agent.agent import AgentError, answer_question, choose_chart
from tests.conftest import requires_db

FREE_QUESTION = "¿Cuántos ingresos hubo por clase de ingreso?"
VALID_SQL = "SELECT admission_class, COUNT(*) AS admissions FROM v_admissions_safe GROUP BY admission_class"


@requires_db
def test_demo_question_uses_rules_without_llm(no_llm):
    r = answer_question("¿Cuántas camas de UCI están ocupadas hoy?")
    assert r["source"] == "rules"
    assert "27" in r["answer"] and "46" in r["answer"]
    assert set(r) >= {"answer", "sql", "columns", "rows", "chart", "recommendations"}


@requires_db
def test_free_question_uses_llm_sql(fake_llm):
    fake = fake_llm(f"```sql\n{VALID_SQL}\n```", "Hay dos clases de ingreso.")
    r = answer_question(FREE_QUESTION)
    assert r["source"] == "llm"
    assert r["columns"] == ["admission_class", "admissions"]
    assert r["answer"] == "Hay dos clases de ingreso."
    assert "LIMIT 200" in r["sql"]
    assert len(fake.calls) == 2  # generar SQL + redactar respuesta


@requires_db
def test_failed_sql_is_retried_once_with_the_error(fake_llm):
    fake = fake_llm("SELECT no_such_column FROM v_admissions_safe", VALID_SQL, "ok")
    r = answer_question(FREE_QUESTION)
    assert r["rows"]
    assert "no_such_column" in fake.calls[1][1]  # el reintento incluye el error


@requires_db
def test_second_sql_failure_raises(fake_llm):
    fake_llm("SELECT a FROM nope", "SELECT b FROM nope")
    with pytest.raises(AgentError):
        answer_question(FREE_QUESTION)


@requires_db
def test_unsafe_llm_sql_is_rejected(fake_llm):
    fake_llm("DELETE FROM admissions", "DROP TABLE admissions")
    with pytest.raises(AgentError):
        answer_question(FREE_QUESTION)


def test_personal_data_question_is_refused_before_calling_llm(fake_llm):
    fake = fake_llm(VALID_SQL)
    with pytest.raises(AgentError):
        answer_question("Dame el nombre y la cédula de los pacientes de UCI")
    assert fake.calls == []


@requires_db
def test_llm_refusal_token_is_reported(fake_llm):
    fake_llm("REFUSE")
    with pytest.raises(AgentError):
        answer_question("Muéstrame quién es el paciente más viejo")


def test_no_rule_and_no_llm_explains_what_to_do(no_llm):
    with pytest.raises(AgentError, match="LLM"):
        answer_question(FREE_QUESTION)


def test_chart_line_for_time_series():
    chart = choose_chart(["census_date", "occupancy_pct"], [["2026-09-01", 50.0], ["2026-09-02", 55.0]])
    assert chart == {"type": "line", "x": "census_date", "y": "occupancy_pct"}


def test_chart_bar_for_few_categories():
    chart = choose_chart(["service", "admissions"], [["Urgencias", 1169], ["Pediatría", 409]])
    assert chart == {"type": "bar", "x": "service", "y": "admissions"}


def test_chart_none_without_numeric_column():
    assert choose_chart(["service"], [["Urgencias"]])["type"] == "none"
