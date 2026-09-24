"""Especificación del plan B por reglas (fallback.py)."""
from app.agent.fallback import match_rule, normalize


def test_normalize_removes_accents_case_and_punctuation():
    assert normalize("¿Cuántas camas de UCI están ocupadas HOY?") == "cuantas camas de uci estan ocupadas hoy"


def test_unrelated_question_has_no_rule():
    assert match_rule("hola, ¿cómo estás?") is None


def test_keywords_match_at_word_start_only():
    # "uci" dentro de "reducir" no debe activar la regla de UCI
    assert match_rule("¿cómo reducir camas ocupadas?") is None


def test_average_occupancy_question_is_not_confused_with_today():
    rule = match_rule("¿Cuál es el promedio de camas ocupadas en UCI?")
    assert rule is not None and rule.name == "avg_occupancy_by_service"


def test_rephrased_question_still_matches():
    rule = match_rule("camas uci ocupadas")
    assert rule is not None and rule.name == "uci_occupancy_today"


def test_surgery_performance_rule_matches():
    rule = match_rule("¿Cuántas cirugías programadas se realizaron?")
    assert rule is not None and rule.name == "surgery_performance"


def test_top_specialties_rule_matches():
    rule = match_rule("¿Cuáles son las especialidades con mayor demanda?")
    assert rule is not None and rule.name == "top_specialties"


def test_avg_stay_rule_matches():
    rule = match_rule("¿Cuál es la estancia promedio en hospitalización?")
    assert rule is not None and rule.name == "avg_length_of_stay"


def test_top_medications_rotation_matches():
    rule = match_rule("rotacion de medicamentos este mes")
    assert rule is not None and rule.name == "top_medications_rotation"


def test_er_root_cause_matches():
    rule = match_rule("¿Cuál es la causa de la espera en urgencias?")
    assert rule is not None and rule.name == "er_root_cause"

