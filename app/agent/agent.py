"""
Orquestador del agente NL2SQL -> POST /api/query.

Responsable: Rol A.

Enrutamiento (docs/01-arquitectura.md §2), en este orden:
    0. Pide datos personales             -> rechazo inmediato (sin llamar al LLM)
    1. Pregunta de definición + término  -> glosario HIS (el LLM solo la redacta; sin LLM, plantilla)
    2. fallback.match_rule(question)     -> SQL fijo (la demo no depende del LLM)
    3. Saludo / ayuda                    -> qué sabe hacer el asistente
    4. LLM con esquema + glosario        -> SQL (validado, ejecutado, 1 reintento) o "TEXT:" conceptual
    Luego: redactar `answer` en tono natural y alerts.recommendations_for(...)
"""
import logging
import re
import sqlite3
from dataclasses import dataclass

from app import alerts, db
from app.agent import fallback, glossary, llm, schema_prompt
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
SMALL_TALK_PATTERN = re.compile(
    r"^(hola|buen(os|as) (dias|tardes|noches)|buenas|gracias|ayuda|help)\b|que puedes hacer|como funciona|"
    r"quien eres|que sabes hacer|en que me (puedes )?ayudar")
CAPABILITIES_MESSAGE = (
    "¡Hola! Soy el asistente de gestión del Hospital Susana López de Valencia. Puedo responder preguntas sobre "
    "los datos del hospital, como la ocupación de camas, los tiempos de espera en urgencias, las cirugías, "
    "el consumo e inventario de medicamentos o la demanda por servicio y especialidad. También te explico "
    "términos del sector salud del glosario HIS, por ejemplo qué es una EPS, el triage o la CIE-10. "
    "Pregúntame como se lo preguntarías a un analista.")
NO_LLM_MESSAGE = ("No tengo una respuesta preparada para esa pregunta y el asistente de IA (LLM) no está configurado. "
                  "Prueba con las preguntas sugeridas o con un término del glosario (por ejemplo, '¿Qué es una EPS?').")
TEXT_PREFIX = schema_prompt.TEXT_PREFIX
NO_CHART = {"type": "none"}


class AgentError(Exception):
    """Error esperado que se muestra al usuario (HTTP 400 con {"error": mensaje})."""


@dataclass(frozen=True)
class _TextReply:
    """El LLM decidió que la pregunta es conceptual y respondió con texto en lugar de SQL."""
    text: str


def answer_question(question: str) -> dict:
    """Responde una pregunta en lenguaje natural.

    Devuelve exactamente:
        {"answer": str, "sql": str ("" si no hubo consulta), "source": "rules" | "llm" | "glossary" | "assistant",
         "columns": list[str], "rows": list[list],
         "chart": {"type": "bar|line|pie|none", "x": str, "y": str},
         "recommendations": list[str], "sources": list[str]}
    Lanza AgentError con un mensaje apto para el usuario.
    """
    question = question.strip()
    normalized = fallback.normalize(question)
    if PERSONAL_DATA_PATTERN.search(normalized):
        raise AgentError(PERSONAL_DATA_MESSAGE)

    if glossary.is_definition_question(question) and (terms := glossary.find_terms(question)):
        return _text_response(_glossary_answer(question, terms), "glossary", glossary.sources_of(terms))

    rule = fallback.match_rule(question)
    if rule:
        sql, columns, rows = _execute(rule.sql)
        answer = rule.summarize([dict(zip(columns, r)) for r in rows]) if rule.summarize and rows \
            else _default_answer(rows)
        return _response(answer, sql, "rules", columns, rows, rule.chart, question)

    if SMALL_TALK_PATTERN.search(normalized):
        return _text_response(CAPABILITIES_MESSAGE, "assistant")

    client = llm.get_llm_client()
    if client is None:
        raise AgentError(NO_LLM_MESSAGE)

    result = _generate_and_execute(client, question)
    if isinstance(result, _TextReply):
        return _text_response(result.text, "llm", [glossary.SOURCE_NAME])
    sql, columns, rows = result
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


def _generate_and_execute(client: llm.LLMClient, question: str) -> "tuple[str, list[str], list[list]] | _TextReply":
    """Pide SQL al LLM y lo ejecuta; si falla, UN reintento enviando el error.
    Si el LLM responde "TEXT: ..." (pregunta conceptual), devuelve _TextReply sin tocar la BD."""
    system = schema_prompt.build_system_prompt()
    raw = _ask(client, system, question).strip()
    if raw.upper().startswith(TEXT_PREFIX):
        return _TextReply(raw[len(TEXT_PREFIX):].strip())
    sql = _extract_sql(raw)
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


def _glossary_answer(question: str, terms: list[dict]) -> str:
    """Definición del glosario. Con LLM se redacta en tono natural; sin LLM (o si falla), plantilla fiel."""
    template = "\n\n".join(glossary.format_entry(t) for t in terms)
    client = llm.get_llm_client()
    if client is None:
        return template
    try:
        text = client.complete(schema_prompt.GLOSSARY_SYSTEM_PROMPT,
                               schema_prompt.build_glossary_prompt(question, template)).strip()
        return text or template
    except Exception as e:
        logger.error("No se pudo redactar la definición con el LLM: %s", e)
        return template


def _text_response(answer: str, source: str, sources: list[str] | None = None) -> dict:
    """Respuesta sin consulta a la BD (glosario, saludo o explicación conceptual)."""
    return {"answer": answer, "sql": "", "source": source, "columns": [], "rows": [],
            "chart": NO_CHART, "recommendations": [], "sources": sources or []}


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
        "sources": ["hospital.db (extracto HIS, mayo a septiembre de 2026)"],
    }


def _is_numeric_column(rows: list[list], index: int) -> bool:
    values = [r[index] for r in rows if r[index] is not None]
    return bool(values) and all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in values)


def _pretty_sql(sql: str) -> str:
    return "\n".join(line.strip() for line in sql.strip().splitlines() if line.strip())
