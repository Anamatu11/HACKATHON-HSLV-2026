"""
Orquestador del agente NL2SQL -> POST /api/query.

Responsable: Rol A.

Pipeline (docs/01-arquitectura.md §2):
    0. Si la pregunta pide datos personales -> rechazo inmediato (sin llamar al LLM).
    1. fallback.match_rule(question)      -> si coincide, SQL fijo (la demo no depende del LLM)
    2. si no: el LLM genera SQL con schema_prompt.build_system_prompt()
    3. sql_guard.validate_sql(sql)         -> solo SELECT, LIMIT, sin PII
    4. db.run_query(sql)                   -> si falla, UN reintento enviando el error al LLM
    5. sql_guard.check_result_columns()
    6. redactar `answer` (resumen de la regla, o LLM)
    7. alerts.recommendations_for(...)
"""
import logging
import re
import sqlite3

from app import alerts, db
from app.agent import fallback, llm, schema_prompt
from app.agent.sql_guard import UnsafeSQLError, check_result_columns, validate_sql
from app.formatting import fmt_number

logger = logging.getLogger(__name__)

PERSONAL_TERMS = r"(nombres?|cedulas?|documentos?|identificacion|fechas? de nacimiento|telefonos?|direccion(es)?|historia clinica)"
PERSONAL_DATA_PATTERN = re.compile(rf"\b{PERSONAL_TERMS}\b.*\bpacientes?\b|\bpacientes?\b.*\b{PERSONAL_TERMS}\b")
TIME_COLUMN_PATTERN = re.compile(r"date|month|day|week|fecha|mes|_at$", re.IGNORECASE)
MAX_BAR_CATEGORIES = 20
CODE_FENCE = re.compile(r"```(?:sql)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)

PERSONAL_DATA_MESSAGE = ("Por privacidad no puedo entregar datos personales de pacientes. "
                         "Puedo responder con cifras agregadas (por servicio, triage, capítulo de diagnóstico...).")


class AgentError(Exception):
    """Error esperado que se muestra al usuario (HTTP 400 con {"error": mensaje})."""


def answer_question(question: str) -> dict:
    """Responde una pregunta en lenguaje natural.

    Devuelve exactamente:
        {"answer": str, "sql": str, "source": "rules" | "llm",
         "columns": list[str], "rows": list[list],
         "chart": {"type": "bar|line|pie|none", "x": str, "y": str},
         "recommendations": list[str]}
    Lanza AgentError con un mensaje apto para el usuario.
    """
    question = question.strip()
    if PERSONAL_DATA_PATTERN.search(fallback.normalize(question)):
        raise AgentError(PERSONAL_DATA_MESSAGE)

    rule = fallback.match_rule(question)
    if rule:
        sql, columns, rows = _execute(rule.sql)
        answer = rule.summarize([dict(zip(columns, r)) for r in rows]) if rule.summarize and rows \
            else _default_answer(rows)
        return _response(answer, sql, "rules", columns, rows, rule.chart, question)

    client = llm.get_llm_client()
    if client is None:
        raise AgentError("No tengo una regla para esa pregunta y no hay un LLM configurado "
                         "(LLM_PROVIDER / API key). Pruebe con una de las preguntas sugeridas.")

    sql, columns, rows = _generate_and_execute(client, question)
    answer = _draft_answer(client, question, columns, rows)
    return _response(answer, sql, "llm", columns, rows, choose_chart(columns, rows), question)


def choose_chart(columns: list[str], rows: list[list]) -> dict:
    """Elige el gráfico con reglas simples: fecha/mes en x -> line; <= 20 categorías -> bar; si no -> none."""
    none = {"type": "none"}
    if not rows or len(columns) < 2:
        return none
    numeric = [c for i, c in enumerate(columns) if i > 0 and _is_numeric_column(rows, i)]
    if not numeric:
        return none
    x, y = columns[0], numeric[0]
    first_x = str(rows[0][0])
    if TIME_COLUMN_PATTERN.search(x) or re.match(r"\d{4}-\d{2}", first_x):
        return {"type": "line", "x": x, "y": y}
    if len(rows) <= MAX_BAR_CATEGORIES:
        return {"type": "bar", "x": x, "y": y}
    return none


# --- Pasos internos --------------------------------------------------------------------

def _execute(sql: str) -> tuple[str, list[str], list[list]]:
    """Valida, ejecuta y revisa columnas. Devuelve el SQL final (con LIMIT) para mostrarlo."""
    safe_sql = validate_sql(sql)
    columns, rows = db.run_query(safe_sql)
    check_result_columns(columns)
    return _pretty_sql(safe_sql), columns, rows


def _generate_and_execute(client: llm.LLMClient, question: str) -> tuple[str, list[str], list[list]]:
    """Pide SQL al LLM y lo ejecuta; si falla, UN reintento enviando el error."""
    system = schema_prompt.build_system_prompt()
    sql = _extract_sql(_ask(client, system, question))
    try:
        return _execute(sql)
    except (UnsafeSQLError, sqlite3.Error) as first_error:
        logger.info("SQL del LLM falló, reintentando: %s", first_error)
        retry_prompt = schema_prompt.build_retry_prompt(question, sql, str(first_error))
        retry_sql = _extract_sql(_ask(client, system, retry_prompt))
    try:
        return _execute(retry_sql)
    except UnsafeSQLError as e:
        raise AgentError(f"La consulta generada no es segura: {e}") from e
    except sqlite3.Error as e:
        logger.warning("Reintento falló: %s | SQL: %s", e, retry_sql)
        raise AgentError("No pude construir una consulta válida para esa pregunta. "
                         "Intente reformularla con más detalle.") from e


def _ask(client: llm.LLMClient, system: str, user: str) -> str:
    try:
        return client.complete(system, user)
    except Exception as e:  # red, cuota, timeout: la demo no debe mostrar un traceback
        logger.error("Fallo del proveedor LLM: %s", e)
        raise AgentError("El asistente de IA no está disponible en este momento. "
                         "Las preguntas frecuentes siguen funcionando.") from e


def _extract_sql(text: str) -> str:
    """Quita bloques ```sql``` y detecta el rechazo del LLM."""
    match = CODE_FENCE.search(text)
    sql = (match.group(1) if match else text).strip()
    if sql.upper().startswith(schema_prompt.REFUSE_TOKEN):
        raise AgentError(PERSONAL_DATA_MESSAGE)
    return sql


def _draft_answer(client: llm.LLMClient, question: str, columns: list[str], rows: list[list]) -> str:
    if not rows:
        return _default_answer(rows)
    try:
        text = client.complete(schema_prompt.ANSWER_SYSTEM_PROMPT,
                               schema_prompt.build_answer_prompt(question, columns, rows)).strip()
        return text or _default_answer(rows)
    except Exception as e:
        logger.error("No se pudo redactar la respuesta con el LLM: %s", e)
        return _default_answer(rows)


def _default_answer(rows: list[list]) -> str:
    if not rows:
        return "No se encontraron datos para esa pregunta en el periodo disponible (mayo a septiembre de 2026)."
    return f"Encontré {fmt_number(len(rows))} resultados. Revise la tabla y el gráfico."


def _recommendations(question: str, columns: list[str], rows: list[list]) -> list[str]:
    try:
        return alerts.recommendations_for(question, columns, rows)
    except NotImplementedError:  # alerts.py lo implementa el Rol B
        return []
    except Exception as e:
        logger.error("Fallo al generar recomendaciones: %s", e)
        return []


def _response(answer: str, sql: str, source: str, columns: list[str], rows: list[list],
              chart: dict, question: str) -> dict:
    return {
        "answer": answer,
        "sql": sql,
        "source": source,
        "columns": columns,
        "rows": rows,
        "chart": chart,
        "recommendations": _recommendations(question, columns, rows),
    }


def _is_numeric_column(rows: list[list], index: int) -> bool:
    values = [r[index] for r in rows if r[index] is not None]
    return bool(values) and all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in values)


def _pretty_sql(sql: str) -> str:
    return "\n".join(line.strip() for line in sql.strip().splitlines() if line.strip())
