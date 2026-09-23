"""
Validación y saneamiento del SQL antes de ejecutarlo.

Responsable: Rol A. Es el punto único de control de seguridad: todo SQL (reglas o LLM) pasa por aquí.
Defensa en capas: además de este guard, la BD se abre en modo solo lectura (db.py).
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

# Estas no tienen uso legítimo en el SQL del agente: se rechazan en cualquier parte de la consulta,
# así un alias (SELECT diagnosis_name AS d) no puede esconderlas. patient_id sí se permite en
# COUNT/JOIN/WHERE, pero no renombrado con alias ni en el resultado.
FORBIDDEN_IN_SQL = tuple(c for c in FORBIDDEN_COLUMNS if c != "patient_id")

# REPLACE solo como sentencia; replace(...) es una función de texto válida.
KEYWORD_PATTERN = re.compile(
    r"\b(" + "|".join(k for k in FORBIDDEN_KEYWORDS if k != "REPLACE") + r")\b|\bREPLACE\b(?!\s*\()",
    re.IGNORECASE,
)
SENSITIVE_PATTERN = re.compile(r"\b(" + "|".join(FORBIDDEN_IN_SQL) + r")\b", re.IGNORECASE)
PATIENT_ID_ALIAS = re.compile(r"\bpatient_id\s+AS\b", re.IGNORECASE)
STRING_LITERAL = re.compile(r"'(?:[^']|'')*'")
COMMENTS = re.compile(r"--[^\n]*|/\*.*?\*/", re.DOTALL)
LIMIT_PATTERN = re.compile(r"\bLIMIT\s+\d+", re.IGNORECASE)


class UnsafeSQLError(ValueError):
    """El SQL o su resultado viola una regla de seguridad. El mensaje se muestra al usuario."""


def validate_sql(sql: str) -> str:
    """Valida y devuelve el SQL listo para ejecutar.

    Reglas:
        - Una sola sentencia (se permite un ';' final).
        - Debe empezar por SELECT o WITH.
        - Ninguna palabra de FORBIDDEN_KEYWORDS ni columna de FORBIDDEN_IN_SQL.
        - Si no tiene LIMIT, agregar LIMIT DEFAULT_LIMIT.
    Lanza UnsafeSQLError si algo falla.
    """
    cleaned = COMMENTS.sub(" ", sql or "").strip().rstrip(";").strip()
    if not cleaned:
        raise UnsafeSQLError("La consulta está vacía.")

    # Las palabras dentro de textos ('%DROP%') no son SQL: se ignoran para los chequeos.
    code_only = STRING_LITERAL.sub("''", cleaned)

    if ";" in code_only:
        raise UnsafeSQLError("Solo se permite una sentencia SQL.")
    if not re.match(r"(SELECT|WITH)\b", code_only, re.IGNORECASE):
        raise UnsafeSQLError("Solo se permiten consultas de lectura (SELECT).")
    if match := KEYWORD_PATTERN.search(code_only):
        raise UnsafeSQLError(f"Operación no permitida: {match.group(0).upper()}.")
    if match := SENSITIVE_PATTERN.search(code_only):
        raise UnsafeSQLError(f"La consulta usa un dato personal o sensible ({match.group(0)}).")
    if PATIENT_ID_ALIAS.search(code_only):
        raise UnsafeSQLError("No se permite devolver identificadores de pacientes.")

    if not LIMIT_PATTERN.search(code_only):
        cleaned = f"{cleaned}\nLIMIT {DEFAULT_LIMIT}"
    return cleaned


def check_result_columns(columns: list[str]) -> None:
    """Lanza UnsafeSQLError si alguna columna del resultado está en FORBIDDEN_COLUMNS."""
    exposed = [c for c in columns if c.lower() in FORBIDDEN_COLUMNS]
    if exposed:
        raise UnsafeSQLError(f"El resultado incluye datos personales ({', '.join(exposed)}).")
