"""
Prompt del sistema para que el LLM genere SQL.

Responsable: Rol A.

Incluye (CLAUDE.md §5):
    - Esquema SOLO de las tablas/vistas permitidas, leído de la BD (sin columnas sensibles).
    - Regla: "hoy" = reference_date; nunca date('now').
    - Preferir vistas derivadas.
    - Responder SOLO con un SELECT de SQLite, o REFUSE si piden datos personales.
    - Few-shot: las preguntas de fallback.RULES con su SQL probado.
"""
from contextlib import closing
from functools import lru_cache

from app import db
from app.agent import fallback
from app.agent.sql_guard import FORBIDDEN_COLUMNS

REFUSE_TOKEN = "REFUSE"
MAX_ROWS_IN_ANSWER_PROMPT = 20

# Tabla/vista permitida -> para qué sirve (ayuda al LLM a elegir bien)
ALLOWED_TABLES = {
    "v_admissions_safe": "ingresos/episodios sin datos personales; diagnóstico solo como capítulo CIE-10 (diagnosis_chapter)",
    "v_occupancy_daily": "ocupación diaria por servicio: occupied_beds, capacity_beds, occupancy_pct, occupancy_physical_pct (>100% = camas virtuales)",
    "bed_capacity": "capacidad ESTIMADA de camas por servicio",
    "wait_times": "espera en urgencias por ingreso: wait_minutes = primera atención - triage; triage_level 1 (emergencia) a 4",
    "stays": "estancias facturadas por unidad de cuidado (UCI Neonatal, UCI Adultos...); NO usar para ocupación de hoy",
    "drug_inventory": "inventario SIMULADO de medicamentos: stock_units, avg_daily_consumption (real), days_of_inventory, expiry_date",
    "medications": "líneas dispensadas de medicamentos e insumos (item_type = 'Medicamento' | 'Dispositivo/Insumo')",
    "services": "líneas de servicios prestados (CUPS), con area (p. ej. 'QUIROFANOS - ...') y specialty",
    "surgery_schedule": "cirugías programadas: schedule_id agrupa una cirugía; in_dataset=1 si cruza con ingresos; was_billed=1 = realizada",
    "triage": "eventos de triage con signos vitales, triage_level y triage_area",
    "first_care": "primera atención médica por ingreso",
    "dataset_meta": "key/value; key='reference_date' es HOY",
}

RULES_TEXT = f"""Eres un analista de datos del Hospital Susana López de Valencia (Popayán, Colombia).
Conviertes preguntas en español a UNA consulta SQLite de solo lectura.

Reglas obligatorias:
1. Responde SOLO con la consulta SQL: sin explicación, sin markdown.
2. Solo SELECT o WITH. Usa únicamente las tablas y columnas del esquema.
3. "Hoy" es (SELECT value FROM dataset_meta WHERE key='reference_date'). NUNCA uses date('now').
   "Este mes" = mismo año-mes que esa fecha; "última semana" = últimos 7 días hasta esa fecha.
4. Las fechas son texto 'YYYY-MM-DD HH:MM:SS': usa substr(), date() y julianday().
5. Prefiere las vistas derivadas (v_occupancy_daily, wait_times, drug_inventory) antes que recalcular.
6. Devuelve agregados con alias claros en inglés (p. ej. COUNT(*) AS admissions). Máximo 200 filas.
7. Si la pregunta pide datos personales o de un paciente individual (nombres, documentos,
   fechas de nacimiento, diagnóstico de una persona), responde exactamente: {REFUSE_TOKEN}
"""


@lru_cache(maxsize=1)
def build_schema_text() -> str:
    """Describe las tablas permitidas con sus columnas (PRAGMA), omitiendo las sensibles."""
    lines = []
    with closing(db.get_connection()) as con:
        for table, purpose in ALLOWED_TABLES.items():
            cols = [f"{name} {ctype}".strip() for _, name, ctype, *_ in con.execute(f"PRAGMA table_info({table})")
                    if name not in FORBIDDEN_COLUMNS]
            lines.append(f"- {table}: {purpose}\n  columnas: {', '.join(cols)}")
    return "\n".join(lines)


def build_few_shot_text() -> str:
    examples = [f"Pregunta: {r.example}\nSQL: {' '.join(r.sql.split())}" for r in fallback.RULES if r.example]
    return "\n\n".join(examples)


def build_system_prompt() -> str:
    """Arma el prompt del sistema: reglas + esquema + few-shot."""
    return (f"{RULES_TEXT}\nFecha de referencia (hoy): {db.get_reference_date()}\n\n"
            f"Esquema:\n{build_schema_text()}\n\nEjemplos:\n\n{build_few_shot_text()}")


def build_retry_prompt(question: str, sql: str, error: str) -> str:
    """Prompt del único reintento: la pregunta, el SQL que falló y el error de SQLite."""
    return (f"Pregunta: {question}\n\nEste SQL falló:\n{sql}\n\nError: {error}\n\n"
            "Corrige la consulta. Responde solo con el SQL corregido.")


ANSWER_SYSTEM_PROMPT = """Eres el asistente de gestión del Hospital Susana López de Valencia.
Redactas respuestas para directivos: 1 a 3 frases en español, con el número clave primero.
Usa solo los datos entregados; no inventes cifras. Formato numérico colombiano (1.169 y 58,7).
Si los datos vienen de drug_inventory, aclara que el inventario es simulado."""


def build_answer_prompt(question: str, columns: list[str], rows: list[list]) -> str:
    """Prompt para redactar la respuesta final con los datos obtenidos."""
    shown = rows[:MAX_ROWS_IN_ANSWER_PROMPT]
    table = "\n".join(" | ".join(map(str, r)) for r in shown)
    extra = f"\n(... {len(rows) - len(shown)} filas más)" if len(rows) > len(shown) else ""
    return f"Pregunta: {question}\n\nColumnas: {' | '.join(columns)}\n{table}{extra}"
