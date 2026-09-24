"""
Cliente LLM intercambiable (patrón Factory) según LLM_PROVIDER.

Responsable: Rol A.

    LLM_PROVIDER=anthropic -> ANTHROPIC_API_KEY   (modelo: LLM_MODEL o DEFAULT_MODELS)
    LLM_PROVIDER=openai    -> OPENAI_API_KEY
    LLM_PROVIDER=none      -> sin LLM: el agente usa solo fallback.py

Futuro (Sprint 3, opcional): LLM_PROVIDER=ollama para modelo local vía API compatible con OpenAI.
"""
import os
from typing import Protocol

DEFAULT_MODELS = {
    "anthropic": "claude-sonnet-5",
    "openai": "gpt-4o-mini",
    "ollama": "sqlcoder:7b",
    "local": "sqlcoder:7b",
}
MAX_TOKENS = 1024
TIMEOUT_SECONDS = 20   # la demo no puede quedarse esperando
MAX_RETRIES = 1


class LLMClient(Protocol):
    def complete(self, system: str, user: str) -> str:
        """Devuelve el texto de la respuesta del modelo."""
        ...


class AnthropicClient:
    def __init__(self, model: str):
        import anthropic  # import perezoso: no se exige si se usa otro proveedor

        self.model = model
        self._client = anthropic.Anthropic(timeout=TIMEOUT_SECONDS, max_retries=MAX_RETRIES)

    def complete(self, system: str, user: str) -> str:
        response = self._client.messages.create(
            model=self.model,
            max_tokens=MAX_TOKENS,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return "".join(block.text for block in response.content if block.type == "text")


class OpenAIClient:
    def __init__(self, model: str, base_url: str | None = None, api_key: str | None = None):
        import openai

        self.model = model
        kwargs = {"timeout": TIMEOUT_SECONDS, "max_retries": MAX_RETRIES}
        if base_url:
            kwargs["base_url"] = base_url
        if api_key:
            kwargs["api_key"] = api_key
        self._client = openai.OpenAI(**kwargs)

    def complete(self, system: str, user: str) -> str:
        response = self._client.chat.completions.create(
            model=self.model,
            temperature=0,  # SQL reproducible
            max_tokens=MAX_TOKENS,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        )
        return response.choices[0].message.content or ""


def get_llm_client() -> LLMClient | None:
    """Devuelve el cliente según LLM_PROVIDER, o None si es 'none' o falta la API key."""
    provider = os.getenv("LLM_PROVIDER", "none").strip().lower()
    model = os.getenv("LLM_MODEL", "").strip() or DEFAULT_MODELS.get(provider, "")
    base_url = os.getenv("OPENAI_BASE_URL") or os.getenv("LLM_BASE_URL")

    if provider == "anthropic" and os.getenv("ANTHROPIC_API_KEY"):
        return AnthropicClient(model)
    if provider == "openai" and (os.getenv("OPENAI_API_KEY") or base_url):
        return OpenAIClient(model, base_url=base_url)
    if provider in ("ollama", "local"):
        base_url = base_url or "http://localhost:11434/v1"
        api_key = os.getenv("OPENAI_API_KEY") or "ollama"
        return OpenAIClient(model or DEFAULT_MODELS["ollama"], base_url=base_url, api_key=api_key)
    return None
