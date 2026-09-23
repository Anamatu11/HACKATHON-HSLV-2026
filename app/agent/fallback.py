"""
Plan B por reglas: preguntas frecuentes -> SQL fijo y probado.

Responsables: Rol A (motor de coincidencia) y Rol B (agregar ~10 reglas más en Sprint 2).

Se usa si: la pregunta coincide con una regla, no hay API key (LLM_PROVIDER=none) o el LLM falla.
La demo NUNCA debe depender del LLM: las 4 preguntas de la demo viven aquí.
Cifras esperadas validadas contra hospital.db (reference_date = 2026-09-21).
"""
from dataclasses import dataclass, field

REF = "(SELECT value FROM dataset_meta WHERE key='reference_date')"


@dataclass(frozen=True)
class Rule:
    name: str
    keywords: tuple[str, ...]     # TODAS deben aparecer en la pregunta normalizada
    sql: str
    chart: dict = field(default_factory=lambda: {"type": "none"})
    answer_template: str = ""     # redacción sin LLM, p. ej. "Hoy hay {occupied_beds} de ..."


RULES: list[Rule] = [
    # Demo 1 -> 27 de 46 (58,7%); 73% sobre camas físicas (37)
    Rule(
        name="uci_occupancy_today",
        keywords=("cama", "uci", "ocupad"),
        sql=f"""SELECT service, occupied_beds, capacity_beds, physical_beds,
                       occupancy_pct, occupancy_physical_pct
                FROM v_occupancy_daily
                WHERE service = 'UCI' AND census_date = {REF}""",
        chart={"type": "bar", "x": "service", "y": "occupied_beds"},
    ),
    # Demo 2 -> 35 medicamentos (inventario SIMULADO)
    Rule(
        name="critical_stock",
        keywords=("medicamento", "inventario"),
        sql="""SELECT item_name, stock_units, avg_daily_consumption, days_of_inventory
               FROM drug_inventory
               WHERE days_of_inventory < 5
               ORDER BY days_of_inventory""",
        chart={"type": "bar", "x": "item_name", "y": "days_of_inventory"},
    ),
    # Demo 3 -> 58,6 min promedio (888 atenciones), desglosado por triage
    Rule(
        name="er_wait_last_week",
        keywords=("espera", "urgencia"),
        sql=f"""SELECT triage_level, COUNT(*) AS attentions, ROUND(AVG(wait_minutes), 1) AS avg_wait_min
                FROM wait_times
                WHERE triage_at >= date({REF}, '-7 day')
                GROUP BY triage_level
                ORDER BY triage_level""",
        chart={"type": "bar", "x": "triage_level", "y": "avg_wait_min"},
    ),
    # Demo 4 -> Urgencias 1.169, Pediatría 409, Hospitalización Adultos 401
    Rule(
        name="admissions_by_service_this_month",
        keywords=("servicio", "ingresad", "mes"),
        sql=f"""SELECT service, COUNT(*) AS admissions
                FROM admissions
                WHERE substr(admission_at, 1, 7) = substr({REF}, 1, 7)
                GROUP BY service
                ORDER BY admissions DESC""",
        chart={"type": "bar", "x": "service", "y": "admissions"},
    ),
    # TODO (Rol B, Sprint 2): ~10 reglas más -> ocupación por servicio, espera por triage,
    # top medicamentos, cirugías realizadas vs programadas, demanda por especialidad...
]


def normalize(text: str) -> str:
    """Minúsculas, sin tildes ni signos (¿?¡!), espacios simples. Así 'Ocupadas' y 'ocupadas' coinciden."""
    raise NotImplementedError


def match_rule(question: str) -> Rule | None:
    """Devuelve la primera regla cuyas keywords aparecen TODAS en la pregunta normalizada, o None."""
    raise NotImplementedError
