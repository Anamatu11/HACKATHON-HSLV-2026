"""Utilidades compartidas por las pruebas."""
from pathlib import Path

import pytest

requires_db = pytest.mark.skipif(not Path("data/hospital.db").exists(),
                                 reason="Falta data/hospital.db: correr el ETL")


class FakeLLM:
    """LLM falso: devuelve las respuestas encoladas en orden y registra cada llamada."""

    def __init__(self, *responses: str):
        self.responses = list(responses)
        self.calls: list[tuple[str, str]] = []

    def complete(self, system: str, user: str) -> str:
        self.calls.append((system, user))
        return self.responses.pop(0) if self.responses else "Respuesta de prueba."


@pytest.fixture
def fake_llm(monkeypatch):
    """Instala un FakeLLM como proveedor: fake_llm('SELECT ...', 'texto respuesta')."""
    from app.agent import llm

    def install(*responses: str) -> FakeLLM:
        fake = FakeLLM(*responses)
        monkeypatch.setattr(llm, "get_llm_client", lambda: fake)
        return fake

    return install


@pytest.fixture
def no_llm(monkeypatch):
    from app.agent import llm
    monkeypatch.setattr(llm, "get_llm_client", lambda: None)
