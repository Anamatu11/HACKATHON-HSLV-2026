"""
Conexión a SQLite en modo SOLO LECTURA.

Responsable: Rol A.

Reglas:
- Abrir siempre con URI `file:<ruta>?mode=ro` (nadie puede escribir en la BD desde la app).
- Timeout de consulta para que una SQL costosa del LLM no congele la demo.
- "Hoy" = dataset_meta.reference_date (2026-09-21). Nunca usar date('now').
"""
import os
import sqlite3
import time
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
QUERY_TIMEOUT_SECONDS = 10          # SQL del agente/LLM: corto, protege la demo
REPORT_QUERY_TIMEOUT_SECONDS = 120  # consultas internas del dashboard (se calculan una vez y se cachean)
PROGRESS_CHECK_OPS = 10_000         # cada cuántas operaciones de SQLite se revisa el timeout


def db_path() -> Path:
    """Ruta de la BD: DB_PATH del .env; si es relativa, se resuelve desde la raíz del repo."""
    path = Path(os.getenv("DB_PATH", "data/hospital.db"))
    return path if path.is_absolute() else ROOT / path


def get_connection() -> sqlite3.Connection:
    """Devuelve una conexión solo-lectura. Falla si la BD no existe (mode=ro no la crea)."""
    return sqlite3.connect(f"file:{db_path().as_posix()}?mode=ro", uri=True, check_same_thread=False)


def run_query(sql: str, params: tuple = (), timeout: float = QUERY_TIMEOUT_SECONDS) -> tuple[list[str], list[list]]:
    """Ejecuta una consulta y devuelve (columns, rows) listos para JSON.

    El SQL del agente pasa antes por sql_guard.validate_sql(); kpis/alerts usan SQL fijo del código.
    Si supera `timeout` segundos, SQLite la interrumpe (sqlite3.OperationalError: interrupted).
    """
    con = get_connection()
    deadline = time.monotonic() + timeout
    con.set_progress_handler(lambda: int(time.monotonic() > deadline), PROGRESS_CHECK_OPS)
    try:
        cur = con.execute(sql, params)
        columns = [d[0] for d in cur.description or []]
        rows = [list(r) for r in cur.fetchall()]
    finally:
        con.close()
    return columns, rows


@lru_cache(maxsize=1)
def get_reference_date() -> str:
    """Devuelve la fecha 'hoy' del dataset (no cambia mientras corre la app)."""
    _, rows = run_query("SELECT value FROM dataset_meta WHERE key = 'reference_date'")
    return rows[0][0]
