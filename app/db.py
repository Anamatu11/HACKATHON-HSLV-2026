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

DB_PATH = os.getenv("DB_PATH", "data/hospital.db")
QUERY_TIMEOUT_SECONDS = 5


def get_connection() -> sqlite3.Connection:
    """Devuelve una conexión solo-lectura a DB_PATH.

    TODO (Rol A):
        sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True, check_same_thread=False)
        y cortar consultas que superen QUERY_TIMEOUT_SECONDS
        (p. ej. con con.set_progress_handler + time.monotonic()).
    """
    raise NotImplementedError


def run_query(sql: str, params: tuple = ()) -> tuple[list[str], list[list]]:
    """Ejecuta una consulta y devuelve (columns, rows) listos para JSON.

    Solo se llama con SQL que ya pasó por sql_guard.validate_sql().
    """
    raise NotImplementedError


def get_reference_date() -> str:
    """Devuelve la fecha 'hoy' del dataset: SELECT value FROM dataset_meta WHERE key='reference_date'."""
    raise NotImplementedError
