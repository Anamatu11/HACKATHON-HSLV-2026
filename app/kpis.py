"""
Consultas del dashboard -> GET /api/kpis.

Responsable: Rol B.

Contrato en docs/01-arquitectura.md §3; SQL de referencia en CLAUDE.md §4.
"Hoy" siempre es REF = dataset_meta.reference_date (2026-09-21), nunca date('now').

Estados de las tarjetas: "ok" | "warning" | "critical" (el frontend los pinta verde/ámbar/rojo).
"""
from functools import lru_cache

from app import db
from app.formatting import fmt_number, pct

REF = "(SELECT value FROM dataset_meta WHERE key='reference_date')"
REF_MONTH = f"substr({REF}, 1, 7)"

OCCUPANCY_WARNING_PCT = 80
OCCUPANCY_CRITICAL_PCT = 90
TRIAGE2_MAX_WAIT_MIN = 30
SURGERY_OK_PCT = 85
SURGERY_WARNING_PCT = 70
TRENDING_SERVICES = ("UCI", "Pediatría", "Hospitalización Adultos", "Gineco-obstetricia")
OCCUPANCY_DAYS = 30
ADMISSIONS_DAYS = 60


def _rows(sql: str) -> list[dict]:
    columns, rows = db.run_query(sql, timeout=db.REPORT_QUERY_TIMEOUT_SECONDS)
    return [dict(zip(columns, r)) for r in rows]


def _status(value: float, warning: float, critical: float, higher_is_worse: bool = True) -> str:
    if higher_is_worse:
        return "critical" if value >= critical else "warning" if value >= warning else "ok"
    return "critical" if value < critical else "warning" if value < warning else "ok"


def _card(card_id: str, label: str, value: float, unit: str, detail: str, status: str) -> dict:
    return {"id": card_id, "label": label, "value": value, "unit": unit, "detail": detail, "status": status}


@lru_cache(maxsize=1)
def get_kpis() -> dict:
    """Arma la respuesta completa del dashboard.

    Se cachea: la BD es de solo lectura y "hoy" es fijo, así que el resultado no cambia mientras
    corre la app (main.py lo precalienta al arrancar). Si se regenera la BD, reiniciar el servidor.
    """
    return {
        "reference_date": db.get_reference_date(),
        "cards": [
            hospital_occupancy(), uci_occupancy(), avg_wait_last_week(),
            critical_stock_count(), surgery_performance(), admissions_this_month(),
        ],
        "series": {
            "occupancy_daily": occupancy_daily_series(),
            "occupancy_by_service": occupancy_by_service_series(),
            "surgery": surgery_series(),
            "admissions_by_service": admissions_by_service_series(),
            "admissions_daily": admissions_daily_series(),
            "wait_by_triage": wait_by_triage_series(),
            "top_medications": medications_rotation_series(most=True),
            "low_medications": medications_rotation_series(most=False),
            "top_specialties": top_specialties_series(),
        },
        "medications_table": medications_table(),
    }


# --- Tarjetas -------------------------------------------------------------------

def hospital_occupancy() -> dict:
    """Ocupación hospitalaria hoy sobre camas FÍSICAS (>100% = se usan camas virtuales)."""
    r = _rows(f"""SELECT SUM(occupied_beds) AS occupied, SUM(physical_beds) AS physical,
                         SUM(capacity_beds) AS capacity
                  FROM v_occupancy_daily WHERE census_date = {REF}""")[0]
    value = pct(r["occupied"], r["physical"])
    detail = (f"{fmt_number(r['occupied'])} pacientes en {fmt_number(r['physical'])} camas físicas · "
              f"{fmt_number(pct(r['occupied'], r['capacity']))}% incluyendo camas virtuales")
    return _card("hospital_occupancy", "Ocupación hospitalaria hoy", value, "%", detail,
                 _status(value, OCCUPANCY_WARNING_PCT, OCCUPANCY_CRITICAL_PCT))


def uci_occupancy() -> dict:
    """Ocupación UCI hoy. Esperado: 27 de 46 (58,7%); 73% sobre 37 camas físicas."""
    r = _rows(f"""SELECT occupied_beds, capacity_beds, physical_beds, occupancy_pct, occupancy_physical_pct
                  FROM v_occupancy_daily WHERE service = 'UCI' AND census_date = {REF}""")[0]
    detail = (f"{r['occupied_beds']} de {r['capacity_beds']} camas · "
              f"{fmt_number(r['occupancy_physical_pct'])}% sobre {r['physical_beds']} físicas")
    return _card("uci_occupancy", "Ocupación UCI hoy", r["occupancy_pct"], "%", detail,
                 _status(r["occupancy_physical_pct"], OCCUPANCY_WARNING_PCT, OCCUPANCY_CRITICAL_PCT))


def avg_wait_last_week() -> dict:
    """Espera promedio en urgencias últimos 7 días. Esperado: 58,6 min, 888 atenciones."""
    r = _rows(f"""SELECT COUNT(*) AS n, ROUND(AVG(wait_minutes), 1) AS avg_wait,
                         ROUND(AVG(CASE WHEN triage_level = 2 THEN wait_minutes END), 1) AS triage2
                  FROM wait_times WHERE triage_at >= date({REF}, '-7 day')""")[0]
    detail = f"{fmt_number(r['n'])} atenciones · triage 2: {fmt_number(r['triage2'])} min (meta ≤ {TRIAGE2_MAX_WAIT_MIN})"
    status = "warning" if r["triage2"] > TRIAGE2_MAX_WAIT_MIN else "ok"
    return _card("avg_wait_7d", "Espera promedio urgencias (7 días)", r["avg_wait"], "min", detail, status)


def critical_stock_count() -> dict:
    """Medicamentos con days_of_inventory < 5 (drug_inventory, SIMULADO). Esperado: 35."""
    r = _rows("""SELECT SUM(days_of_inventory < 5) AS low, SUM(days_of_inventory < 2) AS critical
                 FROM drug_inventory""")[0]
    detail = f"{fmt_number(r['critical'])} con menos de 2 días · inventario simulado"
    status = "critical" if r["critical"] else "warning" if r["low"] else "ok"
    return _card("critical_stock", "Medicamentos con < 5 días", r["low"], "", detail, status)


def surgery_performance() -> dict:
    """% cirugías realizadas vs programadas (solo las que cruzan con ingresos). Esperado: 85,9%."""
    r = _rows("""SELECT COUNT(DISTINCT schedule_id) AS scheduled,
                        COUNT(DISTINCT CASE WHEN was_billed = 1 THEN schedule_id END) AS performed
                 FROM surgery_schedule WHERE in_dataset = 1""")[0]
    value = pct(r["performed"], r["scheduled"])
    detail = (f"{fmt_number(r['performed'])} de {fmt_number(r['scheduled'])} programadas · "
              f"{fmt_number(reprogrammed_admissions())} reprogramaciones")
    return _card("surgery_performed", "Cirugías realizadas", value, "%", detail,
                 _status(value, SURGERY_OK_PCT, SURGERY_WARNING_PCT, higher_is_worse=False))


def admissions_this_month() -> dict:
    rows = _rows(f"""SELECT service, COUNT(*) AS n FROM admissions
                     WHERE substr(admission_at, 1, 7) = {REF_MONTH}
                     GROUP BY service ORDER BY n DESC""")
    total = sum(r["n"] for r in rows)
    detail = f"{rows[0]['service']} lidera con {fmt_number(rows[0]['n'])} · mes en curso (hasta hoy)"
    return _card("admissions_month", "Ingresos del mes", total, "", detail, "ok")


def reprogrammed_admissions() -> int:
    """Ingresos con más de una programación quirúrgica (posibles reprogramaciones)."""
    return _rows("""SELECT COUNT(*) AS n FROM (
                        SELECT admission_id FROM surgery_schedule WHERE in_dataset = 1
                        GROUP BY admission_id HAVING COUNT(DISTINCT schedule_id) > 1)""")[0]["n"]


# --- Series para gráficos ---------------------------------------------------------

def occupancy_daily_series() -> dict:
    """Ocupación física diaria (últimos 30 días) de los servicios más sensibles."""
    services = ", ".join(f"'{s}'" for s in TRENDING_SERVICES)
    # Censo combinado por subservicio (UCI con historia desde estancias facturadas), sumado por servicio
    rows = _rows(f"""SELECT census_date, service,
                            ROUND(100.0 * SUM(occupied_beds) / SUM(physical_beds), 1) AS value
                     FROM v_occupancy_sub_daily
                     WHERE census_date > date({REF}, '-{OCCUPANCY_DAYS} day') AND census_date <= {REF}
                       AND service IN ({services})
                     GROUP BY census_date, service ORDER BY census_date""")
    labels = sorted({r["census_date"] for r in rows})
    by_key = {(r["service"], r["census_date"]): r["value"] for r in rows}
    return {
        "labels": labels,
        "threshold": OCCUPANCY_CRITICAL_PCT,
        "datasets": [{"label": s, "data": [by_key.get((s, d)) for d in labels]} for s in TRENDING_SERVICES],
    }


def occupancy_by_service_series() -> dict:
    rows = _rows(f"""SELECT service, occupied_beds, physical_beds, occupancy_physical_pct AS value
                     FROM v_occupancy_daily WHERE census_date = {REF}
                     ORDER BY occupancy_physical_pct DESC""")
    return {"labels": [r["service"] for r in rows], "data": [r["value"] for r in rows],
            "occupied": [r["occupied_beds"] for r in rows], "physical": [r["physical_beds"] for r in rows],
            "threshold": OCCUPANCY_CRITICAL_PCT}


def surgery_series() -> dict:
    """Programadas vs realizadas por mes (mes del ingreso asociado)."""
    rows = _rows("""SELECT substr(a.admission_at, 1, 7) AS month,
                           COUNT(DISTINCT s.schedule_id) AS scheduled,
                           COUNT(DISTINCT CASE WHEN s.was_billed = 1 THEN s.schedule_id END) AS performed
                    FROM surgery_schedule s JOIN admissions a USING (admission_id)
                    WHERE s.in_dataset = 1 GROUP BY month ORDER BY month""")
    return {"labels": [r["month"] for r in rows],
            "scheduled": [r["scheduled"] for r in rows],
            "performed": [r["performed"] for r in rows],
            "performed_pct": [pct(r["performed"], r["scheduled"]) for r in rows]}


def admissions_by_service_series() -> dict:
    """Ingresos del mes de REF por servicio. Esperado: Urgencias 1.169, Pediatría 409, Hosp. Adultos 401."""
    rows = _rows(f"""SELECT service, COUNT(*) AS n FROM admissions
                     WHERE substr(admission_at, 1, 7) = {REF_MONTH}
                     GROUP BY service ORDER BY n DESC""")
    return {"labels": [r["service"] for r in rows], "data": [r["n"] for r in rows]}


def admissions_daily_series() -> dict:
    """Ingresos diarios (últimos 60 días) con media móvil de 7 días (base de la alerta predictiva)."""
    rows = _rows(f"""SELECT substr(admission_at, 1, 10) AS day, COUNT(*) AS n FROM admissions
                     WHERE admission_at >= date({REF}, '-{ADMISSIONS_DAYS - 1} day')
                       AND substr(admission_at, 1, 10) <= {REF}
                     GROUP BY day ORDER BY day""")
    data = [r["n"] for r in rows]
    moving = [round(sum(data[max(0, i - 6):i + 1]) / len(data[max(0, i - 6):i + 1]), 1) for i in range(len(data))]
    return {"labels": [r["day"] for r in rows], "data": data, "moving_avg_7d": moving}


def wait_by_triage_series() -> dict:
    """Espera promedio por triage: última semana vs histórico previo."""
    rows = _rows(f"""SELECT triage_level,
                            ROUND(AVG(CASE WHEN triage_at >= date({REF}, '-7 day') THEN wait_minutes END), 1) AS last_7d,
                            ROUND(AVG(CASE WHEN triage_at < date({REF}, '-7 day') THEN wait_minutes END), 1) AS historical
                     FROM wait_times WHERE triage_level IS NOT NULL
                     GROUP BY triage_level ORDER BY triage_level""")
    return {"labels": [f"Triage {r['triage_level']}" for r in rows],
            "last_7d": [r["last_7d"] for r in rows], "historical": [r["historical"] for r in rows]}


def medications_rotation_series(most: bool = True, limit: int = 10) -> dict:
    """Medicamentos de mayor (most=True) o menor rotación en los últimos 30 días."""
    rows = _medication_units_last_30d()
    selected = rows[:limit] if most else sorted(rows, key=lambda r: (r["units"], r["item_name"]))[:limit]
    return {"labels": [r["item_name"] for r in selected], "data": [r["units"] for r in selected]}


@lru_cache(maxsize=1)
def _medication_units_last_30d() -> list[dict]:
    """Unidades dispensadas por medicamento (30 días), de mayor a menor. Consulta pesada: una sola vez."""
    return _rows(f"""SELECT item_name, SUM(quantity) AS units FROM medications
                     WHERE item_type = 'Medicamento'
                       AND dispensed_at > date({REF}, '-30 day') AND dispensed_at < date({REF}, '+1 day')
                     GROUP BY item_code, item_name HAVING units > 0
                     ORDER BY units DESC, item_name""")


def top_specialties_series(limit: int = 8) -> dict:
    """Especialidades más solicitadas (ingresos distintos atendidos)."""
    rows = _rows(f"""SELECT specialty, COUNT(DISTINCT admission_id) AS n FROM services
                     WHERE specialty IS NOT NULL AND specialty <> ''
                     GROUP BY specialty ORDER BY n DESC LIMIT {limit}""")
    return {"labels": [r["specialty"] for r in rows], "data": [r["n"] for r in rows]}


def medications_table() -> list[dict]:
    """Inventario (SIMULADO) para la tabla con buscador; el filtro se hace en el navegador."""
    return _rows("""SELECT item_code, item_name, stock_units, avg_daily_consumption, days_of_inventory, expiry_date,
                           CASE WHEN days_of_inventory < 2 THEN 'critical'
                                WHEN days_of_inventory < 5 THEN 'warning' ELSE 'ok' END AS status
                    FROM drug_inventory ORDER BY days_of_inventory, item_name""")
