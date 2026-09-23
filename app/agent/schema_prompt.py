"""
Prompt del sistema para que el LLM genere SQL.

Responsable: Rol A.

Debe incluir (CLAUDE.md §5):
    - Esquema SOLO de las tablas/vistas permitidas (CLAUDE.md §3).
    - Regla: "hoy" = (SELECT value FROM dataset_meta WHERE key='reference_date'); nunca date('now').
    - Preferir vistas derivadas (v_occupancy_daily, wait_times, drug_inventory, v_admissions_safe).
    - Responder SOLO con un SELECT de SQLite, sin explicación ni markdown.
    - Negarse si la pregunta pide datos personales.
    - Few-shot: mínimo las 4 preguntas de la demo (reutilizar fallback.RULES).
"""

ALLOWED_TABLES = (
    "v_admissions_safe", "v_occupancy_daily", "bed_census_daily", "bed_capacity",
    "wait_times", "stays", "drug_inventory", "medications", "services",
    "surgery_schedule", "triage", "first_care", "dataset_meta",
)


def build_system_prompt() -> str:
    """Arma el prompt del sistema: reglas + esquema (PRAGMA table_info de ALLOWED_TABLES) + few-shot."""
    raise NotImplementedError


def build_answer_prompt(question: str, columns: list[str], rows: list[list]) -> str:
    """Prompt para redactar la respuesta final: 1-3 frases en español con el número clave."""
    raise NotImplementedError
