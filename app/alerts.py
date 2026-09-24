"""
Reglas de alertas y recomendaciones -> GET /api/alerts y campo `recommendations` del chat.

Responsable: Rol B.

Reglas simples y explicables (CLAUDE.md §6). Cada alerta:
    {"type": "stock|expiry|occupancy|wait_time|surgery|forecast",
     "severity": "critical|warning|info", "title": str, "detail": str, "action": str}
`detail` explica el dato (y la causa raíz cuando aplica); `action` es la recomendación concreta.
"""
import math
from functools import lru_cache

from app import db
from app.formatting import fmt_number, pct
from app.occupancy import sub_label

REF = "(SELECT value FROM dataset_meta WHERE key='reference_date')"

# Umbrales (ajustar aquí, no dispersos por el código)
STOCK_WARNING_DAYS = 5
STOCK_CRITICAL_DAYS = 2
STOCK_TARGET_DAYS = 15       # cobertura objetivo al reabastecer
MAX_CRITICAL_STOCK_ALERTS = 5
EXPIRY_WINDOW_DAYS = 30
OCCUPANCY_HIGH_PCT = 90      # sobre camas físicas
OCCUPANCY_REASSIGN_PCT = 80  # servicios por debajo pueden ceder personal
TRIAGE2_MAX_WAIT_MIN = 30
TRIAGE3_OVER_AVG_PCT = 20    # % sobre su promedio histórico
DAY_SHIFT = (7, 19)          # turno día 07-19; noche 19-07 (causa raíz)
SURGERY_NOT_PERFORMED_PCT = 10
FORECAST_RECENT_DAYS = 14
FORECAST_BASE_DAYS = 28
FORECAST_MIN_GROWTH_PCT = 15
FORECAST_MIN_DAILY = 3       # ignora capítulos con muy pocos ingresos
MAX_FORECAST_ALERTS = 3
FORECAST_MIN_MED_UNITS = 20     # evita recomendar medicamentos marginales
FORECAST_MIN_MED_SHARE = 0.005  # >= 0,5% de las unidades del capítulo

SEVERITY_RANK = {"critical": 0, "warning": 1, "info": 2}

# Capítulos CIE-10 (primera letra del código) en lenguaje de gestión
CHAPTER_NAMES = {
    "A": "por enfermedades infecciosas", "B": "por enfermedades infecciosas", "C": "oncológicos",
    "D": "hematológicos", "E": "endocrinos", "F": "de salud mental", "G": "neurológicos",
    "H": "de ojo y oído", "I": "cardiovasculares", "J": "respiratorios", "K": "digestivos",
    "L": "de piel", "M": "osteomusculares", "N": "genitourinarios", "O": "obstétricos",
    "P": "perinatales", "Q": "por malformaciones congénitas", "R": "por síntomas generales",
    "S": "por traumatismos", "T": "por traumatismos e intoxicaciones", "Z": "por controles y otros motivos",
}

SHIFT_SQL = (f"CASE WHEN CAST(substr(triage_at, 12, 2) AS INTEGER) >= {DAY_SHIFT[0]} "
             f"AND CAST(substr(triage_at, 12, 2) AS INTEGER) < {DAY_SHIFT[1]} THEN 'día' ELSE 'noche' END")


def _rows(sql: str) -> list[dict]:
    columns, rows = db.run_query(sql, timeout=db.REPORT_QUERY_TIMEOUT_SECONDS)
    return [dict(zip(columns, r)) for r in rows]


def _alert(alert_type: str, severity: str, title: str, detail: str, action: str) -> dict:
    return {"type": alert_type, "severity": severity, "title": title, "detail": detail, "action": action}


def get_alerts() -> list[dict]:
    """Todas las alertas activas a la fecha REF, ordenadas por severidad (orden estable)."""
    return list(_all_alerts())


@lru_cache(maxsize=1)
def _all_alerts() -> tuple[dict, ...]:
    # Cacheado: datos de solo lectura con "hoy" fijo (main.py lo precalienta al arrancar)
    items = (stock_alerts() + occupancy_alerts() + wait_time_alerts() + forecast_alerts()
             + expiry_alerts() + surgery_alerts())
    return tuple(sorted(items, key=lambda a: SEVERITY_RANK[a["severity"]]))


# --- Medicamentos ------------------------------------------------------------------

def stock_alerts() -> list[dict]:
    """Críticos (< 2 días) uno por uno; el resto (< 5 días) resumido en una sola alerta."""
    rows = _rows(f"""SELECT item_name, stock_units, avg_daily_consumption, days_of_inventory
                     FROM drug_inventory WHERE days_of_inventory < {STOCK_WARNING_DAYS}
                     ORDER BY days_of_inventory""")
    critical = [r for r in rows if r["days_of_inventory"] < STOCK_CRITICAL_DAYS]
    alerts = [
        _alert("stock", "critical", f"Reabastecer {r['item_name']}",
               f"Quedan {fmt_number(r['days_of_inventory'])} días de inventario "
               f"(stock {fmt_number(r['stock_units'])} und, consumo diario {fmt_number(r['avg_daily_consumption'], 2)}).",
               f"Solicitar al menos {fmt_number(_units_to_order(r))} unidades para cubrir {STOCK_TARGET_DAYS} días.")
        for r in critical[:MAX_CRITICAL_STOCK_ALERTS]
    ]
    rest = len(rows) - len(alerts)
    if rest:
        alerts.append(_alert(
            "stock", "warning", f"{rest} medicamentos con menos de {STOCK_WARNING_DAYS} días de inventario",
            "Consumo real de los últimos 30 días frente a inventario simulado.",
            "Revisar la tabla de medicamentos y consolidar una orden de compra esta semana."))
    return alerts


def _units_to_order(r: dict) -> int:
    return max(1, math.ceil(r["avg_daily_consumption"] * STOCK_TARGET_DAYS - r["stock_units"]))


def expiry_alerts() -> list[dict]:
    """Stock que vence antes de alcanzar a consumirse -> priorizar uso / redistribuir."""
    rows = _rows(f"""SELECT item_name, stock_units, days_of_inventory, expiry_date,
                            CAST(julianday(expiry_date) - julianday({REF}) AS INTEGER) AS days_to_expiry
                     FROM drug_inventory
                     WHERE expiry_date <= date({REF}, '+{EXPIRY_WINDOW_DAYS} day')
                       AND days_of_inventory > julianday(expiry_date) - julianday({REF})
                     ORDER BY expiry_date""")
    return [
        _alert("expiry", "warning", f"{r['item_name']} vence en {r['days_to_expiry']} días",
               f"Hay {fmt_number(r['days_of_inventory'])} días de inventario pero vence el {r['expiry_date']}: "
               "parte del stock se perdería.",
               "Priorizar su uso y redistribuir a servicios con mayor consumo.")
        for r in rows
    ]


# --- Ocupación ---------------------------------------------------------------------

def occupancy_alerts() -> list[dict]:
    """Servicios >= 90% de camas físicas -> abrir camas / reasignar personal desde servicios holgados."""
    rows = _rows(f"""SELECT service, occupied_beds, physical_beds, occupancy_physical_pct AS pct
                     FROM v_occupancy_daily WHERE census_date = {REF} AND physical_beds > 0
                     ORDER BY occupancy_physical_pct DESC""")
    relaxed = [r for r in reversed(rows) if r["pct"] < OCCUPANCY_REASSIGN_PCT][:2]
    donors = " y ".join(f"{r['service']} ({fmt_number(r['pct'])}%)" for r in relaxed)
    alerts = []
    for r in rows:
        if r["pct"] < OCCUPANCY_HIGH_PCT:
            continue
        full = r["pct"] >= 100
        detail = (f"{r['occupied_beds']} pacientes en {r['physical_beds']} camas físicas ({fmt_number(r['pct'])}%)"
                  + (": se están usando camas virtuales." if r["pct"] > 100
                     else ": sin camas físicas libres." if full else "."))
        action = ("Habilitar camas de expansión y reasignar personal de enfermería desde " + donors + "."
                  if donors else "Habilitar camas de expansión y evaluar reasignación de personal entre servicios.")
        alerts.append(_alert("occupancy", "critical" if full else "warning",
                             f"{r['service']} al {fmt_number(r['pct'])}% de ocupación", detail, action))
    return alerts + critical_unit_alerts()


def critical_unit_alerts() -> list[dict]:
    """Subunidades críticas (UCI/Intermedio/Básico por adultos, neonatal, pediátrica) >= 90%.
    El promedio del servicio puede esconder una unidad llena: hoy UCI está al 73% pero la neonatal al 100%."""
    rows = _rows(f"""SELECT service, sub_service, occupied_beds, physical_beds, occupancy_physical_pct AS pct
                     FROM v_occupancy_sub_daily
                     WHERE census_date = {REF} AND physical_beds > 0
                       AND service IN ('UCI', 'Cuidado Intermedio')
                       AND occupancy_physical_pct >= {OCCUPANCY_HIGH_PCT}
                     ORDER BY occupancy_physical_pct DESC""")
    return [
        _alert("occupancy", "critical" if r["pct"] >= 100 else "warning",
               f"{sub_label(r['sub_service'])} al {fmt_number(r['pct'])}% de ocupación",
               f"{r['occupied_beds']} pacientes en {r['physical_beds']} camas físicas de {sub_label(r['sub_service'])}, "
               f"aunque el servicio {r['service']} en conjunto tiene camas libres.",
               "Revisar criterios de egreso y traslado a intermedio, y activar la red de referencia "
               "si ingresa un paciente que requiera esta unidad.")
        for r in rows
    ]


# --- Tiempos de espera -------------------------------------------------------------

def wait_time_alerts() -> list[dict]:
    """Triage 2 > 30 min o triage 3 > promedio histórico +20% -> alerta con causa raíz."""
    rows = {r["triage_level"]: r for r in _rows(f"""
        SELECT triage_level,
               ROUND(AVG(CASE WHEN triage_at >= date({REF}, '-7 day') THEN wait_minutes END), 1) AS last_7d,
               ROUND(AVG(CASE WHEN triage_at < date({REF}, '-7 day') THEN wait_minutes END), 1) AS historical
        FROM wait_times WHERE triage_level IN (2, 3) GROUP BY triage_level""")}
    alerts = []
    t2 = rows.get(2)
    if t2 and t2["last_7d"] > TRIAGE2_MAX_WAIT_MIN:
        alerts.append(_alert(
            "wait_time", "critical" if t2["last_7d"] > 2 * TRIAGE2_MAX_WAIT_MIN else "warning",
            f"Triage 2 espera {fmt_number(t2['last_7d'])} min (meta ≤ {TRIAGE2_MAX_WAIT_MIN})",
            _wait_root_cause(2),
            "Asignar un médico adicional en urgencias durante el turno con mayor demanda."))
    t3 = rows.get(3)
    if t3 and t3["historical"] and t3["last_7d"] > t3["historical"] * (1 + TRIAGE3_OVER_AVG_PCT / 100):
        alerts.append(_alert(
            "wait_time", "warning",
            f"Triage 3 espera {fmt_number(t3['last_7d'])} min (histórico {fmt_number(t3['historical'])})",
            _wait_root_cause(3),
            "Reforzar el turno señalado y habilitar consulta rápida para triage 3."))
    return alerts


def _wait_root_cause(level: int) -> str:
    """Compara volumen/día y espera por turno (última semana vs histórico) y el área con más demanda."""
    shifts = _rows(f"""
        SELECT {SHIFT_SQL} AS shift,
               SUM(triage_at >= date({REF}, '-7 day')) / 7.0 AS recent_per_day,
               SUM(triage_at < date({REF}, '-7 day')) /
                   (julianday(date({REF}, '-7 day')) - julianday(MIN(triage_at))) AS hist_per_day,
               ROUND(AVG(CASE WHEN triage_at >= date({REF}, '-7 day') THEN wait_minutes END), 1) AS recent_wait
        FROM wait_times WHERE triage_level = {level} GROUP BY shift""")
    worst = max(shifts, key=lambda s: s["recent_wait"] or 0)
    change = pct(worst["recent_per_day"] - worst["hist_per_day"], worst["hist_per_day"])
    area = _rows(f"""SELECT triage_area, COUNT(*) AS n FROM wait_times
                     WHERE triage_level = {level} AND triage_at >= date({REF}, '-7 day')
                     GROUP BY triage_area ORDER BY n DESC LIMIT 1""")
    trend = "más" if change >= 0 else "menos"
    text = (f"Causa probable: el turno {worst['shift']} concentra la mayor espera "
            f"({fmt_number(worst['recent_wait'])} min) con {fmt_number(round(worst['recent_per_day'], 1))} "
            f"pacientes/día, {fmt_number(abs(change))}% {trend} que su promedio histórico.")
    if area:
        text += f" El área {area[0]['triage_area']} aporta la mayor demanda."
    return text


# --- Cirugías -----------------------------------------------------------------------

def surgery_alerts() -> list[dict]:
    """% de programaciones no realizadas, peor mes y reprogramaciones."""
    total = _rows("""SELECT COUNT(DISTINCT schedule_id) AS scheduled,
                            COUNT(DISTINCT CASE WHEN was_billed = 1 THEN schedule_id END) AS performed
                     FROM surgery_schedule WHERE in_dataset = 1""")[0]
    months = _rows("""SELECT substr(a.admission_at, 1, 7) AS month,
                             100.0 * COUNT(DISTINCT CASE WHEN s.was_billed = 1 THEN s.schedule_id END)
                                   / COUNT(DISTINCT s.schedule_id) AS performed_pct
                      FROM surgery_schedule s JOIN admissions a USING (admission_id)
                      WHERE s.in_dataset = 1 GROUP BY month ORDER BY performed_pct LIMIT 1""")
    reprogrammed = _rows("""SELECT COUNT(*) AS n FROM (
                                SELECT admission_id FROM surgery_schedule WHERE in_dataset = 1
                                GROUP BY admission_id HAVING COUNT(DISTINCT schedule_id) > 1)""")[0]["n"]
    not_performed = total["scheduled"] - total["performed"]
    not_pct = pct(not_performed, total["scheduled"])
    detail = (f"{fmt_number(not_performed)} de {fmt_number(total['scheduled'])} programaciones no se realizaron "
              f"({fmt_number(not_pct)}%); {fmt_number(reprogrammed)} ingresos tuvieron reprogramaciones.")
    if months:
        detail += f" Mes con menor cumplimiento: {months[0]['month']} ({fmt_number(round(months[0]['performed_pct'], 1))}%)."
    severity = "warning" if not_pct > SURGERY_NOT_PERFORMED_PCT else "info"
    return [_alert("surgery", severity, f"{fmt_number(not_pct)}% de cirugías programadas no realizadas", detail,
                   "Confirmar pacientes 24 h antes y reasignar los turnos de quirófano liberados a la lista de espera.")]


# --- Predictiva (valor añadido) ----------------------------------------------------

def forecast_alerts() -> list[dict]:
    """Capítulos CIE-10 cuyo promedio diario de las últimas 2 semanas supera en >= 15% al de las 4 anteriores."""
    base_start = FORECAST_RECENT_DAYS + FORECAST_BASE_DAYS - 1
    rows = _rows(f"""
        SELECT diagnosis_chapter AS chapter,
               SUM(admission_at >= date({REF}, '-{FORECAST_RECENT_DAYS - 1} day')) / {FORECAST_RECENT_DAYS}.0 AS recent,
               SUM(admission_at >= date({REF}, '-{base_start} day')
                   AND admission_at < date({REF}, '-{FORECAST_RECENT_DAYS - 1} day')) / {FORECAST_BASE_DAYS}.0 AS base
        FROM admissions WHERE diagnosis_chapter IS NOT NULL
        GROUP BY diagnosis_chapter""")
    trending = []
    for r in rows:
        growth = pct(r["recent"] - r["base"], r["base"]) if r["base"] else 0
        if r["recent"] >= FORECAST_MIN_DAILY and growth >= FORECAST_MIN_GROWTH_PCT:
            trending.append((growth, r))
    # Orden por impacto (ingresos extra por día), no por %: +30% sobre 3/día pesa menos que +24% sobre 8/día
    trending.sort(key=lambda t: t[1]["recent"] - t[1]["base"], reverse=True)

    alerts = []
    for growth, r in trending[:MAX_FORECAST_ALERTS]:
        name = CHAPTER_NAMES.get(r["chapter"], f"capítulo {r['chapter']}")
        meds = _top_medications_for_chapter(r["chapter"])
        action = (f"Asegurar stock de: {', '.join(meds)}." if meds
                  else "Anticipar camas y personal para el servicio que recibe estos pacientes.")
        alerts.append(_alert(
            "forecast", "warning" if growth >= 20 else "info",
            f"Tendencia al alza: ingresos {name} (+{fmt_number(growth)}%)",
            f"Promedio de {fmt_number(round(r['recent'], 1))} ingresos/día en las últimas 2 semanas vs "
            f"{fmt_number(round(r['base'], 1))} en las 4 anteriores. Proyección próxima semana: "
            f"~{fmt_number(round(r['recent'] * 7))} ingresos (capítulo CIE-10 {r['chapter']}).",
            action))
    return alerts


def _top_medications_for_chapter(chapter: str, limit: int = 3) -> list[str]:
    """Medicamentos CARACTERÍSTICOS del capítulo: los de mayor 'lift' (participación en el capítulo /
    participación en todo el hospital). Así no salen siempre acetaminofén y suero, que dominan en todos."""
    rows = _medication_units_by_chapter()
    total_all = sum(r["units"] for r in rows)
    units_all: dict[str, int] = {}
    for r in rows:
        units_all[r["item_name"]] = units_all.get(r["item_name"], 0) + r["units"]
    in_chapter = [r for r in rows if r["chapter"] == chapter]
    total_ch = sum(r["units"] for r in in_chapter)
    if not total_ch:
        return []
    min_units = max(FORECAST_MIN_MED_UNITS, total_ch * FORECAST_MIN_MED_SHARE)
    scored = [((r["units"] / total_ch) / (units_all[r["item_name"]] / total_all), r["item_name"])
              for r in in_chapter if r["units"] >= min_units]
    return [name for _, name in sorted(scored, reverse=True)[:limit]]


@lru_cache(maxsize=1)
def _medication_units_by_chapter() -> list[dict]:
    """Unidades dispensadas (30 días) por capítulo CIE-10 y medicamento. Consulta pesada: una sola vez."""
    return _rows(f"""SELECT a.diagnosis_chapter AS chapter, m.item_name, SUM(m.quantity) AS units
                     FROM medications m
                     JOIN (SELECT admission_id, diagnosis_chapter FROM admissions
                           WHERE diagnosis_chapter IS NOT NULL) a USING (admission_id)
                     WHERE m.item_type = 'Medicamento' AND m.dispensed_at > date({REF}, '-30 day')
                     GROUP BY a.diagnosis_chapter, m.item_name
                     ORDER BY a.diagnosis_chapter, units DESC""")


# --- Recomendaciones para el chat --------------------------------------------------

def recommendations_for(question: str, columns: list[str], rows: list[list]) -> list[str]:
    """Recomendaciones para una respuesta del chat según el tema detectado por sus columnas."""
    cols = [c.lower() for c in columns]
    if "days_of_inventory" in cols:
        return _stock_recommendations(cols, rows)
    if any("occup" in c for c in cols):
        return [a["action"] for a in occupancy_alerts()[:2]]
    if any("wait" in c for c in cols):
        return [f"{a['title']}: {a['action']}" for a in wait_time_alerts()]
    if {"scheduled", "performed"} & set(cols):
        return [a["action"] for a in surgery_alerts()]
    if "admissions" in cols:
        return [f"{a['title']}. {a['action']}" for a in forecast_alerts()[:1]]
    return []


def _stock_recommendations(cols: list[str], rows: list[list]) -> list[str]:
    days_i = cols.index("days_of_inventory")
    name_i = cols.index("item_name") if "item_name" in cols else None
    low = [r for r in rows if r[days_i] is not None and r[days_i] < STOCK_WARNING_DAYS]
    recs = [f"Reabastecer {r[name_i] if name_i is not None else 'el medicamento'}: quedan "
            f"{fmt_number(r[days_i])} días de inventario." for r in low[:3]]
    if len(low) > 3:
        recs.append(f"Consolidar una orden de compra para los {len(low)} medicamentos en riesgo.")
    return recs
