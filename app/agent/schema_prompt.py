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
from app.agent import fallback, glossary
from app.agent.sql_guard import FORBIDDEN_COLUMNS

REFUSE_TOKEN = "REFUSE"
TEXT_PREFIX = "TEXT:"
MAX_ROWS_IN_ANSWER_PROMPT = 20

# Tabla/vista permitida -> para qué sirve (ayuda al LLM a elegir bien)
ALLOWED_TABLES = {
    "v_admissions_safe": "ingresos/episodios sin datos personales; diagnóstico solo como capítulo CIE-10 (diagnosis_chapter)",
    "v_occupancy_daily": "ocupación diaria por servicio: occupied_beds, capacity_beds, occupancy_pct, occupancy_physical_pct (>100% = camas virtuales)",
    "bed_capacity": "capacidad ESTIMADA de camas por servicio",
    "v_occupancy_sub_daily": "ocupación diaria por servicio Y subservicio (UCI Adultos/Neonatal/Pediátrica, Intermedio...). "
                             "PREFERIRLA para promedios históricos: en unidades críticas combina cama registrada y estancias "
                             "facturadas (occupied_beds = la mayor). Sumar occupied_beds y physical_beds por día para nivel servicio",
    "bed_capacity_sub": "capacidad ESTIMADA por servicio y subservicio",
    "specialty_census_daily": "pacientes hospitalizados presentes por día atendidos por cada especialidad (specialty_group, "
                              "p. ej. 'MEDICINA INTERNA'); no tiene capacidad de camas",
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
   EXCEPCIÓN: si la pregunta es conceptual y no necesita datos (qué significa un término del sector salud,
   cómo se calcula un indicador del panel, qué limitaciones tienen los datos), responde "{TEXT_PREFIX} " seguido
   de una explicación breve (2 a 4 frases), natural y en español, apoyada en el glosario y en las
   definiciones de indicadores de abajo. No menciones tablas ni SQL en ese texto.
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
    """Arma el prompt del sistema: reglas + esquema + indicadores + glosario + few-shot."""
    return (f"{RULES_TEXT}\nFecha de referencia (hoy): {db.get_reference_date()}\n\n"
            f"Esquema:\n{build_schema_text()}\n\n{KPI_DEFINITIONS}\n\n{glossary.glossary_prompt_text()}\n\n"
            f"Ejemplos:\n\n{build_few_shot_text()}")


def build_retry_prompt(question: str, sql: str, error: str) -> str:
    """Prompt del único reintento: la pregunta, el SQL que falló y el error de SQLite."""
    return (f"Pregunta: {question}\n\nEste SQL falló:\n{sql}\n\nError: {error}\n\n"
            "Corrige la consulta. Responde solo con el SQL corregido.")


ANSWER_SYSTEM_PROMPT = """Eres el asistente de gestión del Hospital Susana López de Valencia y le hablas a un
directivo o jefe de servicio, como lo haría un analista cercano y claro.

Cómo responder:
- Empieza con la respuesta directa y el número clave. Luego, si aporta, una frase que lo interprete
  (qué significa, con qué se compara, qué conviene mirar).
- 1 a 3 frases en español natural. Nada de jerga de bases de datos: no menciones tablas, columnas ni SQL.
- Si aparece un término técnico del sector (triage, EPS, CIE-10, régimen), explícalo en pocas palabras.
- Usa solo los datos entregados; no inventes cifras. Formato numérico colombiano (1.169 y 58,7).
- Si los datos son de inventario de medicamentos, aclara que el inventario es simulado."""

GLOSSARY_SYSTEM_PROMPT = """Eres el asistente del Hospital Susana López de Valencia. Explicas términos del sector
salud colombiano a directivos que no son del área clínica.

Cómo responder:
- 2 a 4 frases, en español natural y cercano, como se lo explicarías a un colega.
- Básate SOLO en las definiciones entregadas (glosario oficial HIS); no inventes datos.
- Si preguntan por una diferencia, contrasta los términos directamente.
- Si la definición trae una nota "En este panel", menciónala: conecta el concepto con los datos del hospital."""

# Los indicadores del panel viven en glossary.PANEL_TERMS (una sola fuente); aquí solo las limitaciones.
KPI_DEFINITIONS = """Limitaciones de los datos (decirlas cuando apliquen):
- Servicio del ingreso = cama registrada; los traslados internos no se ven.
- Datos de mayo a septiembre de 2026; septiembre llega hasta el 21 (hoy)."""


def build_glossary_prompt(question: str, definitions: str) -> str:
    return f"Pregunta: {question}\n\nDefiniciones del glosario oficial:\n{definitions}"


def build_answer_prompt(question: str, columns: list[str], rows: list[list]) -> str:
    """Prompt para redactar la respuesta final con los datos obtenidos."""
    shown = rows[:MAX_ROWS_IN_ANSWER_PROMPT]
    table = "\n".join(" | ".join(map(str, r)) for r in shown)
    extra = f"\n(... {len(rows) - len(shown)} filas más)" if len(rows) > len(shown) else ""
    return f"Pregunta: {question}\n\nColumnas: {' | '.join(columns)}\n{table}{extra}"
