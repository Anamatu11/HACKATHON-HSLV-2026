"""
Validación y saneamiento del SQL antes de ejecutarlo.

Responsable: Rol A. Es el punto único de control de seguridad: todo SQL (reglas o LLM) pasa por aquí.
"""
import re

DEFAULT_LIMIT = 200

FORBIDDEN_KEYWORDS = (
    "INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "ATTACH", "DETACH",
    "PRAGMA", "CREATE", "REPLACE", "VACUUM", "REINDEX",
)

# Columnas que NUNCA pueden salir en un resultado (datos personales / diagnóstico específico).
# Los agregados sí se permiten: COUNT por diagnosis_chapter está bien.
FORBIDDEN_COLUMNS = (
    "patient_id", "birth_date", "diagnosis_name", "diagnosis_code", "bed_code", "bed_name",
)

KEYWORD_PATTERN = re.compile(r"\b(" + "|".join(FORBIDDEN_KEYWORDS) + r")\b", re.IGNORECASE)


class UnsafeSQLError(ValueError):
    """El SQL o su resultado viola una regla de seguridad. El mensaje se muestra al usuario."""


def validate_sql(sql: str) -> str:
    """Valida y devuelve el SQL listo para ejecutar.

    Reglas:
        - Una sola sentencia (se permite un ';' final).
        - Debe empezar por SELECT o WITH.
        - Ninguna palabra de FORBIDDEN_KEYWORDS.
        - Si no tiene LIMIT, agregar LIMIT DEFAULT_LIMIT.
    Lanza UnsafeSQLError si algo falla.
    """
    raise NotImplementedError


def check_result_columns(columns: list[str]) -> None:
    """Lanza UnsafeSQLError si alguna columna del resultado está en FORBIDDEN_COLUMNS."""
    raise NotImplementedError
