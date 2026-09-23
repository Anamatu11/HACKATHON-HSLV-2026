"""
Cliente LLM intercambiable (patrón Factory) según LLM_PROVIDER.

Responsable: Rol A.

    LLM_PROVIDER=anthropic -> ANTHROPIC_API_KEY
    LLM_PROVIDER=openai    -> OPENAI_API_KEY
    LLM_PROVIDER=none      -> sin LLM: el agente usa solo fallback.py

Futuro (Sprint 3, opcional): LLM_PROVIDER=ollama para modelo local vía API compatible con OpenAI.
Usar temperature=0 para generar SQL reproducible.
"""
import os
from typing import Protocol


class LLMClient(Protocol):
    def complete(self, system: str, user: str) -> str:
        """Devuelve el texto de la respuesta del modelo."""
        ...


class AnthropicClient:
    def complete(self, system: str, user: str) -> str:
        raise NotImplementedError


class OpenAIClient:
    def complete(self, system: str, user: str) -> str:
        raise NotImplementedError


def get_llm_client() -> LLMClient | None:
    """Devuelve el cliente según LLM_PROVIDER, o None si es 'none' o falta la API key."""
    provider = os.getenv("LLM_PROVIDER", "none").lower()
    if provider == "anthropic" and os.getenv("ANTHROPIC_API_KEY"):
        return AnthropicClient()
    if provider == "openai" and os.getenv("OPENAI_API_KEY"):
        return OpenAIClient()
    return None
