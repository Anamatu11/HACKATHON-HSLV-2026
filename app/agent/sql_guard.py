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

# Columnas que NUNCA pueden salir en un resultado (datos personales).
FORBIDDEN_COLUMNS = ("patient_id", "birth_date", "bed_code", "bed_name")

# Estas no tienen uso legítimo en el SQL del agente: se rechazan en cualquier parte de la consulta,
# así un alias no puede esconderlas. patient_id sí se permite en COUNT/JOIN/WHERE, pero no
# renombrado con alias ni en el resultado.
FORBIDDEN_IN_SQL = tuple(c for c in FORBIDDEN_COLUMNS if c != "patient_id")

# Diagnóstico específico (CIE-10 completo): permitido SOLO en consultas agregadas
# ("¿cuántas apendicitis?", "top 10 diagnósticos de UCI"), nunca una fila por ingreso con su diagnóstico.
DIAGNOSIS_COLUMNS = ("diagnosis_code", "diagnosis_name")
# Identificadores de fila: con diagnóstico no pueden ir sueltos en el SELECT ni en el GROUP BY finales
# (dentro de una función sí: COUNT(DISTINCT admission_id), substr(admission_at, 1, 7)).
ROW_LEVEL_COLUMNS = ("admission_id", "admission_number", "patient_id", "line_id", "triage_id", "schedule_id",
                     "admission_at", "hospitalization_at", "last_activity_at", "first_care_at", "triage_at",
                     "performed_at", "dispensed_at", "age_years")

# REPLACE solo como sentencia; replace(...) es una función de texto válida.
KEYWORD_PATTERN = re.compile(
    r"\b(" + "|".join(k for k in FORBIDDEN_KEYWORDS if k != "REPLACE") + r")\b|\bREPLACE\b(?!\s*\()",
    re.IGNORECASE,
)
SENSITIVE_PATTERN = re.compile(r"\b(" + "|".join(FORBIDDEN_IN_SQL) + r")\b", re.IGNORECASE)
PATIENT_ID_ALIAS = re.compile(r"\bpatient_id\s+AS\b", re.IGNORECASE)
DIAGNOSIS_PATTERN = re.compile(r"\b(" + "|".join(DIAGNOSIS_COLUMNS) + r")\b", re.IGNORECASE)
DIAGNOSIS_ALIAS = re.compile(r"\b(" + "|".join(DIAGNOSIS_COLUMNS) + r")\s+AS\b", re.IGNORECASE)
ROW_LEVEL_PATTERN = re.compile(r"\b(" + "|".join(ROW_LEVEL_COLUMNS) + r")\b|(?<![\w.])\*", re.IGNORECASE)
AGGREGATE_CALL = re.compile(r"\b(COUNT|SUM|AVG|MIN|MAX|TOTAL)\s*\(", re.IGNORECASE)
TOP_SELECT = re.compile(r"\bSELECT\b(.*?)(?:\bFROM\b|$)", re.IGNORECASE | re.DOTALL)
TOP_GROUP_BY = re.compile(r"\bGROUP\s+BY\b(.*?)(?=\bHAVING\b|\bORDER\b|\bLIMIT\b|\bUNION\b|$)",
                          re.IGNORECASE | re.DOTALL)
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
    if DIAGNOSIS_PATTERN.search(code_only):
        _check_diagnosis_is_aggregated(code_only)

    if not LIMIT_PATTERN.search(code_only):
        cleaned = f"{cleaned}\nLIMIT {DEFAULT_LIMIT}"
    return cleaned


def _top_level(sql: str) -> str:
    """Borra el contenido entre paréntesis (subconsultas, CTE, argumentos de funciones) y deja el nivel 0.
    'SELECT a, COUNT(x) FROM (SELECT ...)' -> 'SELECT a, COUNT( ) FROM ( )'."""
    out, depth = [], 0
    for ch in sql:
        if ch == ")":
            depth = max(depth - 1, 0)
        out.append(ch if depth == 0 or ch in "()" else " ")
        if ch == "(":
            depth += 1
    return "".join(out)


def _top_level_groups(sql: str) -> list[str]:
    """Contenido de cada paréntesis de nivel 0: 'SELECT (SELECT 1), (SELECT 2)' -> ['SELECT 1', 'SELECT 2']."""
    groups, depth, start = [], 0, 0
    for i, ch in enumerate(sql):
        if ch == "(":
            if depth == 0:
                start = i + 1
            depth += 1
        elif ch == ")" and depth > 0:
            depth -= 1
            if depth == 0:
                groups.append(sql[start:i])
    return groups


def _check_diagnosis_is_aggregated(code_only: str) -> None:
    """Con diagnóstico específico, la consulta FINAL debe ser agregada y sin identificadores de fila.

    Las CTE/subconsultas pueden trabajar por ingreso (quedan dentro de paréntesis); lo que se valida es
    lo que sale al usuario: cada SELECT de nivel 0 (incluidas las partes de un UNION).
    """
    if DIAGNOSIS_ALIAS.search(code_only):
        raise UnsafeSQLError("No se permite renombrar el diagnóstico con un alias.")
    if re.search(r"\bGROUP_CONCAT\s*\(", code_only, re.IGNORECASE):
        raise UnsafeSQLError("No se permite concatenar diagnósticos por ingreso.")
    _check_statement(code_only)


def _check_statement(sql: str) -> None:
    top = _top_level(sql)
    if not re.search(r"\bFROM\b", top, re.IGNORECASE):
        # SELECT sin FROM: sus columnas son subconsultas escalares -> cada una con diagnóstico debe ser agregada
        if match := ROW_LEVEL_PATTERN.search(top):
            raise UnsafeSQLError(f"Con diagnóstico específico no se devuelven datos por ingreso ({match.group(0)}).")
        for sub in _top_level_groups(sql):
            if DIAGNOSIS_PATTERN.search(sub) and re.match(r"\s*(SELECT|WITH)\b", sub, re.IGNORECASE):
                _check_statement(sub)
        return
    group_by = " ".join(TOP_GROUP_BY.findall(top))
    for select_list in TOP_SELECT.findall(top):
        if not (AGGREGATE_CALL.search(select_list) or group_by.strip()):
            raise UnsafeSQLError("El diagnóstico específico solo se consulta en cifras agregadas "
                                 "(conteos, porcentajes, promedios), no por ingreso.")
        if match := ROW_LEVEL_PATTERN.search(select_list):
            raise UnsafeSQLError(f"Con diagnóstico específico no se devuelven datos por ingreso ({match.group(0)}).")
    if match := ROW_LEVEL_PATTERN.search(group_by):
        raise UnsafeSQLError(f"Con diagnóstico específico no se agrupa por ingreso ({match.group(0)}).")


def check_result_columns(columns: list[str]) -> None:
    """Lanza UnsafeSQLError si el resultado trae datos personales, o diagnóstico junto a un identificador."""
    lowered = [c.lower() for c in columns]
    exposed = [c for c in lowered if c in FORBIDDEN_COLUMNS]
    if exposed:
        raise UnsafeSQLError(f"El resultado incluye datos personales ({', '.join(exposed)}).")
    if any(c in DIAGNOSIS_COLUMNS for c in lowered) and any(c in ROW_LEVEL_COLUMNS for c in lowered):
        raise UnsafeSQLError("El resultado mezcla diagnóstico con datos por ingreso.")
