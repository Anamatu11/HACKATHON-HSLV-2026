"""Glosario HIS: detección de términos y de preguntas de definición."""
from app.agent.glossary import GLOSSARY, find_terms, is_definition_question


def names(entries):
    return [e["term"] for e in entries]


def test_glossary_covers_the_pdf_sections():
    categories = {e["category"] for e in GLOSSARY}
    assert {"Siglas y sistemas", "Documentos de identificación", "Afiliación y aseguramiento",
            "Proceso de atención", "Signos vitales", "Términos del modelo de datos"} <= categories
    assert len(GLOSSARY) >= 30


def test_finds_acronym_case_insensitive_when_long():
    assert names(find_terms("¿Qué es una eps?")) == ["EPS"]


def test_finds_several_terms():
    assert set(names(find_terms("¿Cuál es la diferencia entre EPS e IPS?"))) == {"EPS", "IPS"}


def test_short_acronyms_require_uppercase():
    # "ti" en "pensando en ti" no es Tarjeta de Identidad
    assert find_terms("¿qué significa pensando en ti?") == []
    assert names(find_terms("¿Qué significa TI?")) == ["TI"]


def test_finds_multiword_terms_and_aliases():
    assert names(find_terms("¿Qué es la frecuencia respiratoria?")) == ["Frecuencia respiratoria"]
    assert names(find_terms("explícame qué es el régimen subsidiado")) == ["Régimen (de afiliación)"]
    assert "Triage" in names(find_terms("¿Qué es el triage?"))


def test_definition_question_detection():
    assert is_definition_question("¿Qué es una EPS?")
    assert is_definition_question("¿Qué significa CUPS?")
    assert is_definition_question("Explícame el triage")
    assert is_definition_question("¿Cuál es la diferencia entre EPS e IPS?")
    assert not is_definition_question("¿Qué servicio tiene más pacientes ingresados este mes?")
    assert not is_definition_question("¿Cuántas camas de UCI están ocupadas hoy?")
