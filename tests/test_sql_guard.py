"""
Especificación de sql_guard (Rol A). Fallan hasta que se implemente validate_sql / check_result_columns.

Ejecutar desde la raíz:  python -m pytest -q
"""
import pytest

from app.agent.sql_guard import UnsafeSQLError, check_result_columns, validate_sql


@pytest.mark.parametrize("sql", [
    "DROP TABLE admissions",
    "DELETE FROM admissions",
    "UPDATE drug_inventory SET stock_units = 0",
    "PRAGMA table_info(admissions)",
    "ATTACH DATABASE 'x.db' AS x",
    "SELECT 1; DROP TABLE admissions",
])
def test_rejects_non_select_or_multiple_statements(sql):
    with pytest.raises(UnsafeSQLError):
        validate_sql(sql)


def test_adds_limit_when_missing():
    assert "LIMIT 200" in validate_sql("SELECT service FROM v_admissions_safe").upper()


def test_keeps_existing_limit():
    assert validate_sql("SELECT service FROM v_admissions_safe LIMIT 5").upper().count("LIMIT") == 1


def test_accepts_with_clause():
    validate_sql("WITH t AS (SELECT 1 AS n) SELECT n FROM t")


@pytest.mark.parametrize("column", ["patient_id", "birth_date", "diagnosis_name", "bed_name"])
def test_rejects_personal_columns(column):
    with pytest.raises(UnsafeSQLError):
        check_result_columns(["service", column])


@pytest.mark.parametrize("sql", [
    "SELECT diagnosis_name AS d, COUNT(*) FROM triage GROUP BY 1",   # alias para esconder la columna
    "SELECT bed_name FROM bed_capacity",
    "SELECT birth_date FROM triage",
])
def test_rejects_sensitive_identifiers_anywhere_in_sql(sql):
    with pytest.raises(UnsafeSQLError):
        validate_sql(sql)


def test_rejects_patient_id_renamed_with_alias():
    with pytest.raises(UnsafeSQLError):
        validate_sql("SELECT patient_id AS x FROM triage")


def test_allows_patient_id_inside_count():
    validate_sql("SELECT COUNT(DISTINCT patient_id) AS patients FROM triage")


def test_ignores_keywords_inside_string_literals():
    validate_sql("SELECT COUNT(*) FROM medications WHERE item_name LIKE '%DROP%'")


def test_allows_replace_function():
    validate_sql("SELECT replace(service, ' ', '_') AS s FROM v_admissions_safe")


def test_allows_aggregated_columns():
    check_result_columns(["diagnosis_chapter", "admissions"])
