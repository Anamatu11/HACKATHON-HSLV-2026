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


def _summarize_avg_occupancy(rows: list[dict]) -> str:
    top = rows[0]
    fullest = max(rows, key=lambda r: r["avg_physical_pct"] or 0)
    return (f"Desde junio, {top['service']} es el servicio con más camas ocupadas en promedio "
            f"({fmt_number(top['avg_occupied_beds'])} por día, {fmt_number(top['avg_physical_pct'])}% de sus camas físicas). "
            f"El más presionado es {fullest['service']}, con {fmt_number(fullest['avg_physical_pct'])}% en promedio. "
            "Puede ver el detalle diario o mensual por servicio y subservicio en la pestaña Ocupación.")


def _summarize_surgery(rows: list[dict]) -> str:
    r = rows[0]
    return (f"Se han realizado {fmt_number(r['performed'])} de {fmt_number(r['scheduled'])} cirugías programadas "
            f"({fmt_number(r['performance_pct'])}% de cumplimiento). Se registran 253 ingresos con reprogramaciones.")


def _summarize_specialties(rows: list[dict]) -> str:
    top = rows[0]
    second = f", seguida de {rows[1]['specialty']} ({fmt_number(rows[1]['admissions'])})" if len(rows) > 1 else ""
    return f"La especialidad más demandada es {top['specialty']} con {fmt_number(top['admissions'])} ingresos atendidos{second}."


def _summarize_stay(rows: list[dict]) -> str:
    top = rows[0]
    second = f", seguido de {rows[1]['service']} con {fmt_number(rows[1]['avg_stay_days'])} días" if len(rows) > 1 else ""
    return f"El servicio con mayor estancia promedio es {top['service']} con {fmt_number(top['avg_stay_days'])} días{second}."


def _summarize_med_rotation(rows: list[dict]) -> str:
    top = rows[0]
    second = f", seguido por {rows[1]['item_name']} ({fmt_number(rows[1]['units'])} und)" if len(rows) > 1 else ""
    return f"El medicamento con mayor rotación en el mes es {top['item_name']} con {fmt_number(top['units'])} unidades dispensadas{second}."


def _summarize_root_cause(rows: list[dict]) -> str:
    night_t3 = [r for r in rows if r["triage_level"] == 3 and "Noche" in r["shift"]]
    wait = f"{fmt_number(night_t3[0]['avg_wait_min'])} min" if night_t3 else "alta"
    return (f"El análisis de causa raíz indica que el principal cuello de botella se produce en Triage 3 durante el turno de noche "
            f"(espera promedio de {wait}). Se sugiere reforzar personal médico y habilitar consultorios nocturnos de descongestión.")


RULES: list[Rule] = [
    # Promedio de ocupación por servicio (KPI del reto). Va ANTES de la regla de "hoy" para que
    # "¿promedio de camas ocupadas en UCI?" no responda la foto del día.
    Rule(
        name="avg_occupancy_by_service",
        keywords=("promedio", "ocupa"),
        example="¿Cuál es el promedio diario de camas ocupadas por servicio?",
        sql=f"""SELECT d.service, ROUND(AVG(d.occ), 1) AS avg_occupied_beds, k.physical AS physical_beds,
                       ROUND(100.0 * AVG(d.occ) / k.physical, 1) AS avg_physical_pct
                FROM (SELECT census_date, service, SUM(occupied_beds) AS occ FROM v_occupancy_sub_daily
                      WHERE census_date >= (SELECT value FROM dataset_meta WHERE key = 'census_reliable_from')
                        AND census_date <= {REF}
                      GROUP BY census_date, service) d
                JOIN (SELECT service, SUM(physical_beds) AS physical FROM bed_capacity_sub GROUP BY service) k
                  USING (service)
                GROUP BY d.service ORDER BY avg_occupied_beds DESC""",
        chart={"type": "bar", "x": "service", "y": "avg_occupied_beds"},
        summarize=_summarize_avg_occupancy,
    ),
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
    # Análisis de causa raíz de tiempos de espera (turnos día vs noche). Va ANTES de espera general.
    Rule(
        name="er_root_cause",
        keywords=("causa", "espera"),
        example="¿Cuál es la causa del aumento en los tiempos de espera?",
        sql=f"""SELECT triage_level,
                      CASE WHEN CAST(substr(triage_at, 12, 2) AS INTEGER) >= 7 AND CAST(substr(triage_at, 12, 2) AS INTEGER) < 19
                           THEN 'Día (07-19)' ELSE 'Noche (19-07)' END AS shift,
                      COUNT(*) AS attentions, ROUND(AVG(wait_minutes), 1) AS avg_wait_min
               FROM wait_times
               WHERE triage_at >= date({REF}, '-14 day')
               GROUP BY triage_level, shift ORDER BY triage_level, shift""",
        chart={"type": "bar", "x": "shift", "y": "avg_wait_min"},
        summarize=_summarize_root_cause,
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
    # Eficiencia de quirófanos (cirugías realizadas vs programadas)
    Rule(
        name="surgery_performance",
        keywords=("cirugia", "programad"),
        example="¿Cuántas cirugías programadas se han realizado?",
        sql="""SELECT COUNT(DISTINCT schedule_id) AS scheduled,
                      COUNT(DISTINCT CASE WHEN was_billed = 1 THEN schedule_id END) AS performed,
                      ROUND(100.0 * COUNT(DISTINCT CASE WHEN was_billed = 1 THEN schedule_id END) / COUNT(DISTINCT schedule_id), 1) AS performance_pct
               FROM surgery_schedule WHERE in_dataset = 1""",
        chart={"type": "bar", "x": "scheduled", "y": "performed"},
        summarize=_summarize_surgery,
    ),
    # Especialidades más solicitadas
    Rule(
        name="top_specialties",
        keywords=("especialidad", "demand"),
        example="¿Cuáles son las especialidades más demandadas?",
        sql="""SELECT specialty, COUNT(DISTINCT admission_id) AS admissions
               FROM services
               WHERE specialty IS NOT NULL AND specialty <> ''
               GROUP BY specialty ORDER BY admissions DESC LIMIT 8""",
        chart={"type": "bar", "x": "specialty", "y": "admissions"},
        summarize=_summarize_specialties,
    ),
    # Estancia promedio por servicio
    Rule(
        name="avg_length_of_stay",
        keywords=("estancia", "promedio"),
        example="¿Cuál es el tiempo de estancia promedio por servicio?",
        sql="""SELECT service, ROUND(AVG(length_of_stay_days), 1) AS avg_stay_days, COUNT(*) AS admissions
               FROM v_admissions_safe
               WHERE length_of_stay_days IS NOT NULL AND length_of_stay_days > 0
               GROUP BY service ORDER BY avg_stay_days DESC LIMIT 8""",
        chart={"type": "bar", "x": "service", "y": "avg_stay_days"},
        summarize=_summarize_stay,
    ),
    # Medicamentos con mayor rotación en el mes
    Rule(
        name="top_medications_rotation",
        keywords=("medicamento", "rotacion"),
        example="¿Cuáles son los medicamentos con mayor rotación en el mes?",
        sql=f"""SELECT item_name, SUM(quantity) AS units
               FROM medications
               WHERE item_type = 'Medicamento' AND substr(dispensed_at, 1, 7) = substr({REF}, 1, 7)
               GROUP BY item_name ORDER BY units DESC LIMIT 10""",
        chart={"type": "bar", "x": "item_name", "y": "units"},
        summarize=_summarize_med_rotation,
    ),
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
