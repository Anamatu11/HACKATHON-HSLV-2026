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


def test_glossary_question_answers_without_llm(no_llm):
    r = answer_question("¿Qué es una EPS?")
    assert r["source"] == "glossary"
    assert "Entidad Promotora de Salud" in r["answer"]
    assert r["sql"] == "" and r["rows"] == [] and r["chart"]["type"] == "none"
    assert r["sources"] == ["Glosario de Términos del Sector Salud HIS"]


def test_glossary_answer_is_drafted_naturally_by_llm(fake_llm):
    fake = fake_llm("Una EPS es, en pocas palabras, la aseguradora de salud.")
    r = answer_question("¿Qué es una EPS?")
    assert r["answer"] == "Una EPS es, en pocas palabras, la aseguradora de salud."
    assert "Entidad Promotora de Salud" in fake.calls[0][1]   # el LLM recibe la definición oficial


def test_glossary_falls_back_to_template_if_llm_fails(monkeypatch):
    from app.agent import llm

    class Broken:
        def complete(self, system, user):
            raise RuntimeError("sin red")

    monkeypatch.setattr(llm, "get_llm_client", lambda: Broken())
    assert "Entidad Promotora de Salud" in answer_question("¿Qué es una EPS?")["answer"]


def test_panel_indicator_question_answers_without_llm(no_llm):
    r = answer_question("¿Qué es la ocupación física?")
    assert r["source"] == "glossary"
    assert "camas físicas" in r["answer"]
    assert r["sources"] == ["Definiciones de indicadores del panel HSLV"]


def test_greeting_explains_capabilities(no_llm):
    r = answer_question("Hola, ¿qué puedes hacer?")
    assert r["source"] == "assistant"
    assert "glosario" in r["answer"].lower()


@requires_db
def test_llm_can_answer_conceptual_questions_with_text(fake_llm):
    fake = fake_llm("TEXT: La ocupación física se calcula sobre camas reales, sin contar las virtuales.")
    r = answer_question("¿Por qué la ocupación física puede pasar de 100%?")
    assert r["source"] == "llm" and r["sql"] == ""
    assert r["answer"].startswith("La ocupación física")
    assert "Glosario" in fake.calls[0][0]   # el glosario va en el prompt del sistema


def test_chart_line_for_time_series():
    chart = choose_chart(["census_date", "occupancy_pct"], [["2026-09-01", 50.0], ["2026-09-02", 55.0]])
    assert chart == {"type": "line", "x": "census_date", "y": "occupancy_pct"}


def test_chart_bar_for_few_categories():
    chart = choose_chart(["service", "admissions"], [["Urgencias", 1169], ["Pediatría", 409]])
    assert chart == {"type": "bar", "x": "service", "y": "admissions"}


def test_chart_none_without_numeric_column():
    assert choose_chart(["service"], [["Urgencias"]])["type"] == "none"
