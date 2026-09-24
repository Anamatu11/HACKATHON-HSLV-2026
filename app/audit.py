"""
Bitácora de auditoría del asistente IA (append-only, encadenada con SHA-256).

Responsable: Rol A.

Cada consulta a /api/query (respondida o bloqueada) y cada informe PDF descargado se registra como una línea
JSON en `data/audit.jsonl` (AUDIT_PATH, fuera de git). Cada registro guarda el hash del anterior
(`prev_hash`) y el suyo (`hash`): si alguien edita o borra una línea, la cadena deja de cuadrar
y `verify_chain()` lo detecta. El informe PDF se arma SOLO con lo registrado aquí, no con datos del navegador.
"""
import hashlib
import json
import os
import threading
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.agent import llm

COLOMBIA = timezone(timedelta(hours=-5), "COT")     # Colombia no tiene horario de verano
GENESIS_HASH = "0" * 64
_lock = threading.Lock()


def _path() -> Path:
    return Path(os.getenv("AUDIT_PATH", "data/audit.jsonl"))


def now_iso() -> str:
    return datetime.now(COLOMBIA).isoformat(timespec="seconds")


def result_fingerprint(columns: list, rows: list) -> str:
    """Huella SHA-256 del resultado: permite comprobar que la tabla del informe es la que se consultó."""
    payload = json.dumps({"columns": columns, "rows": rows}, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode()).hexdigest()


def _record_hash(record: dict) -> str:
    body = {k: v for k, v in record.items() if k != "hash"}
    return hashlib.sha256(json.dumps(body, ensure_ascii=False, sort_keys=True, default=str).encode()).hexdigest()


def _read_all() -> list[dict]:
    try:
        lines = _path().read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return []
    return [json.loads(line) for line in lines if line.strip()]


def _append(record: dict) -> dict:
    with _lock:
        records = _read_all()
        record["prev_hash"] = records[-1]["hash"] if records else GENESIS_HASH
        record["hash"] = _record_hash(record)
        path = _path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
    return record


def _engine(source: str) -> str:
    if source != "llm":
        return {"rules": "Consulta verificada (plan B por reglas, sin IA)",
                "glossary": "Glosario HIS", "assistant": "Asistente"}.get(source, source)
    provider = os.getenv("LLM_PROVIDER", "none").strip().lower()
    model = os.getenv("LLM_MODEL", "").strip() or llm.DEFAULT_MODELS.get(provider, "")
    return f"IA generativa ({provider}: {model})"


def log_query(user: dict, question: str, result: dict | None = None, error: str | None = None) -> dict:
    """Registra una consulta. Con `result` = respondida; con `error` = rechazada/bloqueada."""
    record = {
        "id": uuid.uuid4().hex[:12], "event": "query", "at": now_iso(),
        "username": user["username"], "name": user.get("name", ""), "role": user.get("role", ""),
        "question": question, "status": "error" if error else "ok", "error": error,
    }
    if result is not None:
        record.update({
            "source": result.get("source"), "engine": _engine(result.get("source", "")),
            "answer": result.get("answer"), "sql": result.get("sql"),
            "columns": result.get("columns", []), "rows": result.get("rows", []),
            "chart": result.get("chart"), "recommendations": result.get("recommendations", []),
            "row_count": len(result.get("rows", [])),
            "result_sha256": result_fingerprint(result.get("columns", []), result.get("rows", [])),
        })
    return _append(record)


def log_report(user: dict, query_id: str) -> dict:
    return _append({"id": uuid.uuid4().hex[:12], "event": "report", "at": now_iso(),
                    "username": user["username"], "name": user.get("name", ""), "role": user.get("role", ""),
                    "query_id": query_id, "status": "ok"})


def find_query(query_id: str) -> dict | None:
    return next((r for r in _read_all() if r.get("event") == "query" and r.get("id") == query_id), None)


def recent_events(username: str, limit: int = 10) -> list[dict]:
    """Últimos eventos del usuario (consultas y descargas), del más reciente al más antiguo."""
    return [r for r in reversed(_read_all()) if r.get("username") == username][:limit]


def verify_chain() -> tuple[bool, int]:
    """(íntegra, número de registros). False si una línea fue editada, borrada o reordenada."""
    prev = GENESIS_HASH
    records = _read_all()
    for r in records:
        if r.get("prev_hash") != prev or _record_hash(r) != r.get("hash"):
            return False, len(records)
        prev = r["hash"]
    return True, len(records)
