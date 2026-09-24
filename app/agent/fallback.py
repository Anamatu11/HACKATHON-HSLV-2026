"""
Plan B por reglas: preguntas frecuentes -> SQL fijo y probado.

Responsables: Rol A (motor de coincidencia) y Rol B (agregar ~10 reglas más en Sprint 2).

Se usa si: la pregunta coincide con una regla, no hay API key (LLM_PROVIDER=none) o el LLM falla.
La demo NUNCA debe depender del LLM: las 4 preguntas de la demo viven aquí.
Cifras esperadas validadas contra hospital.db (reference_date = 2026-09-21).

Para agregar una regla: nombre, keywords (inicio de palabra, sin tildes; TODAS deben aparecer),
SQL probado en SQLite, gráfico, una pregunta de ejemplo (sirve de few-shot al LLM) y una
función `summarize(rows_as_dicts) -> str` que redacte la respuesta sin LLM.
"""
import re
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass, field

from app.formatting import fmt_number

REF = "(SELECT value FROM dataset_meta WHERE key='reference_date')"


@dataclass(frozen=True)
class Rule:
    name: str
    keywords: tuple[str, ...]     # TODAS deben aparecer al inicio de alguna palabra de la pregunta
    sql: str
    chart: dict = field(default_factory=lambda: {"type": "none"})
    example: str = ""             # pregunta de ejemplo: few-shot para el LLM y documentación
    summarize: Callable[[list[dict]], str] | None = None   # redacción sin LLM


# --- Redacción de las respuestas de la demo -----------------------------------------

def _summarize_uci(rows: list[dict]) -> str:
    r = rows[0]
    return (f"Hoy hay {r['occupied_beds']} de {r['capacity_beds']} camas de UCI ocupadas "
            f"({fmt_number(r['occupancy_pct'])}%). Sobre las {r['physical_beds']} camas físicas "
            f"(sin camas virtuales) la ocupación es {fmt_number(r['occupancy_physical_pct'])}%.")


def _summarize_stock(rows: list[dict]) -> str:
    if not rows:
        return "No hay medicamentos con menos de 5 días de inventario."
    worst = rows[0]
    return (f"Hay {len(rows)} medicamentos con menos de 5 días de inventario. El más crítico es "
            f"{worst['item_name']} con {fmt_number(worst['days_of_inventory'])} días. "
            "Nota: el inventario es simulado a partir del consumo real.")


def _summarize_wait(rows: list[dict]) -> str:
    total = sum(r["attentions"] for r in rows)
    worst = max(rows, key=lambda r: r["avg_wait_min"])
    return (f"En la última semana la espera promedio en urgencias fue de "
            f"{fmt_number(rows[0]['overall_avg_wait_min'])} minutos ({fmt_number(total)} atenciones). "
            f"El triage {worst['triage_level']} tuvo la mayor espera: {fmt_number(worst['avg_wait_min'])} min "
            "(el triage 1 es el más urgente y el 4 el menos urgente).")


def _summarize_services(rows: list[dict]) -> str:
    top, *rest = rows
    others = " y ".join(f"{r['service']} ({fmt_number(r['admissions'])})" for r in rest[:2])
    return (f"{top['service']} es el servicio con más ingresos este mes ({fmt_number(top['admissions'])})"
            + (f", seguido de {others}." if others else "."))


RULES: list[Rule] = [
    # Demo 1 -> 27 de 46 (58,7%); 73% sobre camas físicas (37)
    Rule(
        name="uci_occupancy_today",
        keywords=("cama", "uci", "ocupad"),
        example="¿Cuántas camas de UCI están ocupadas hoy?",
        sql=f"""SELECT service, occupied_beds, capacity_beds, physical_beds,
                       occupancy_pct, occupancy_physical_pct
                FROM v_occupancy_daily
                WHERE service = 'UCI' AND census_date = {REF}""",
        chart={"type": "bar", "x": "service", "y": "occupied_beds"},
        summarize=_summarize_uci,
    ),
    # Demo 2 -> 35 medicamentos (inventario SIMULADO)
    Rule(
        name="critical_stock",
        keywords=("medicamento", "inventario"),
        example="¿Cuáles son los medicamentos con menos de 5 días de inventario?",
        sql="""SELECT item_name, stock_units, avg_daily_consumption, days_of_inventory
               FROM drug_inventory
               WHERE days_of_inventory < 5
               ORDER BY days_of_inventory""",
        chart={"type": "bar", "x": "item_name", "y": "days_of_inventory"},
        summarize=_summarize_stock,
    ),
    # Demo 3 -> 58,6 min promedio (888 atenciones), desglosado por triage
    Rule(
        name="er_wait_last_week",
        keywords=("espera", "urgencia"),
        example="¿Cuál es el tiempo de espera promedio en urgencias en la última semana?",
        sql=f"""SELECT triage_level, COUNT(*) AS attentions, ROUND(AVG(wait_minutes), 1) AS avg_wait_min,
                       ROUND(SUM(SUM(wait_minutes)) OVER () / SUM(COUNT(*)) OVER (), 1) AS overall_avg_wait_min
                FROM wait_times
                WHERE triage_at >= date({REF}, '-7 day')
                GROUP BY triage_level
                ORDER BY triage_level""",
        chart={"type": "bar", "x": "triage_level", "y": "avg_wait_min"},
        summarize=_summarize_wait,
    ),
    # Demo 4 -> Urgencias 1.169, Pediatría 409, Hospitalización Adultos 401
    Rule(
        name="admissions_by_service_this_month",
        keywords=("servicio", "ingresad", "mes"),
        example="¿Qué servicio tiene más pacientes ingresados este mes?",
        sql=f"""SELECT service, COUNT(*) AS admissions
                FROM admissions
                WHERE substr(admission_at, 1, 7) = substr({REF}, 1, 7)
                GROUP BY service
                ORDER BY admissions DESC""",
        chart={"type": "bar", "x": "service", "y": "admissions"},
        summarize=_summarize_services,
    ),
    # TODO (Rol B, Sprint 2): ~10 reglas más -> ocupación por servicio, espera por triage,
    # top medicamentos, cirugías realizadas vs programadas, demanda por especialidad...
]


def normalize(text: str) -> str:
    """Minúsculas, sin tildes ni signos (¿?¡!), espacios simples. Así 'Ocupadas' y 'ocupadas' coinciden."""
    no_accents = "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))
    return " ".join(re.sub(r"[^a-z0-9]+", " ", no_accents.lower()).split())


def match_rule(question: str) -> Rule | None:
    """Devuelve la primera regla cuyas keywords aparecen TODAS (al inicio de una palabra), o None."""
    text = normalize(question)
    for rule in RULES:
        if all(re.search(rf"\b{re.escape(kw)}", text) for kw in rule.keywords):
            return rule
    return None
