"""Especificación del plan B por reglas (fallback.py)."""
from app.agent.fallback import match_rule, normalize


def test_normalize_removes_accents_case_and_punctuation():
    assert normalize("¿Cuántas camas de UCI están ocupadas HOY?") == "cuantas camas de uci estan ocupadas hoy"


def test_unrelated_question_has_no_rule():
    assert match_rule("hola, ¿cómo estás?") is None


def test_keywords_match_at_word_start_only():
    # "uci" dentro de "reducir" no debe activar la regla de UCI
    assert match_rule("¿cómo reducir camas ocupadas?") is None


def test_rephrased_question_still_matches():
    rule = match_rule("camas uci ocupadas")
    assert rule is not None and rule.name == "uci_occupancy_today"
