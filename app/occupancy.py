"""
Ocupación hospitalaria: promedio diario/mensual de camas ocupadas por servicio, subservicio o especialidad.
-> GET /api/occupancy/filters y GET /api/occupancy

Responsable: Rol B.

Fuentes (ver etl/build_db.py):
- v_occupancy_sub_daily: censo diario por subservicio. En unidades críticas (UCI, Intermedio, Básico Neonatal)
  toma el MAYOR entre la cama registrada y las estancias facturadas, porque ambas subcuentan por causas distintas.
- specialty_census_daily: pacientes hospitalizados atendidos por cada grupo de especialidad (p. ej. Medicina
  Interna, que no es un servicio de camas). No tiene capacidad: no hay % de ocupación.

Todos los filtros se validan contra listas conocidas y se pasan como parámetros SQL (nunca concatenados).
"""
import re
from datetime import date, timedelta
from functools import lru_cache

from app import db
from app.formatting import pct

HIGH_OCCUPANCY_PCT = 90
CRITICAL_SERVICES = {"UCI", "Cuidado Intermedio", "Cuidado Básico Neonatal"}
GRANULARITIES = {"daily", "monthly"}
DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")
RECENT_UNDERCOUNT_DAYS = 14   # en unidades críticas, las estancias recientes aún no están facturadas

# Nombres legibles de los subservicios (el HIS los trae en mayúsculas)
SUB_LABELS = {
    "UNIDAD DE CUIDADOS INTENSIVOS ADULTOS": "UCI Adultos",
    "UNIDAD DE CUIDADO INTENSIVO NEONATAL": "UCI Neonatal",
    "UNIDAD DE CUIDADO INTENSIVO PEDIATRICO": "UCI Pediátrica",
    "UNIDAD DE CUIDADO INTERMEDIO ADULTOS": "Intermedio Adultos",
    "UNIDAD DE CUIDADO INTERMEDIO NEONATAL": "Intermedio Neonatal",
    "UNIDAD DE CUIDADO INTERMEDIO PEDIATRICO": "Intermedio Pediátrico",
    "UNIDAD DE CUIDAD BASICO NEONATAL": "Básico Neonatal",
    "HOSPITALIZACION 1": "Hospitalización 1", "HOSPITALIZACION 2": "Hospitalización 2",
    "HOSPITALIZACION 3": "Hospitalización 3",
    "URGENCIAS ADULTOS": "Urgencias Adultos", "URGENCIAS PEDIATRIA": "Urgencias Pediatría",
    "URGENCIAS GINECOLOGIA": "Urgencias Ginecología", "EMERGENCIA ADULTOS": "Emergencia Adultos",
    "EMERGENCIA PEDIATRIA": "Emergencia Pediatría", "PEDIATRIA": "Pediatría",
    "GINECO OBSTETRICIA": "Gineco-obstetricia", "RECUPERACION ADULTOS": "Recuperación Adultos",
    "SALA PARTOS": "Sala de Partos",
}
SPECIALTY_LABELS = {"PEDIATRA": "Pediatría", "ORTOPEDIA Y TRAUMATOLOGIA": "Ortopedia y Traumatología",
                    "GINECOLOGIA Y OBSTETRICIA": "Ginecología y Obstetricia",
                    "MEDICINA CRITICA Y CUIDADO INTENSIVO": "Medicina Crítica y Cuidado Intensivo",
                    "FONOAUDIOLOGIA": "Fonoaudiología", "CIRUGIA GENERAL": "Cirugía General"}


def sub_label(sub_service: str) -> str:
    return SUB_LABELS.get(sub_service, sub_service.title())


def specialty_label(group: str) -> str:
    return SPECIALTY_LABELS.get(group, group.title())


def _rows(sql: str, params: tuple = ()) -> list[dict]:
    columns, rows = db.run_query(sql, params, timeout=db.REPORT_QUERY_TIMEOUT_SECONDS)
    return [dict(zip(columns, r)) for r in rows]


def _meta(key: str) -> str:
    return _rows("SELECT value FROM dataset_meta WHERE key = ?", (key,))[0]["value"]


@lru_cache(maxsize=1)
def get_filters() -> dict:
    """Opciones del filtro: servicios con subservicios (y camas), especialidades y rango de fechas."""
    caps = _rows("""SELECT service, sub_service, capacity_beds, physical_beds FROM bed_capacity_sub
                    ORDER BY service, physical_beds DESC""")
    services: dict[str, dict] = {}
    for c in caps:
        s = services.setdefault(c["service"], {"service": c["service"], "physical_beds": 0,
                                               "capacity_beds": 0, "sub_services": []})
        s["physical_beds"] += c["physical_beds"]
        s["capacity_beds"] += c["capacity_beds"]
        s["sub_services"].append({"value": c["sub_service"], "label": sub_label(c["sub_service"]),
                                  "physical_beds": c["physical_beds"], "capacity_beds": c["capacity_beds"]})
    specialties = [r["specialty_group"] for r in _rows(
        """SELECT specialty_group, AVG(patients) AS avg FROM specialty_census_daily
           GROUP BY specialty_group ORDER BY avg DESC""")]
    bounds = _rows("SELECT MIN(census_date) AS first FROM bed_census_sub_daily")[0]
    return {
        "services": sorted(services.values(), key=lambda s: -s["physical_beds"]),
        "specialties": [{"value": s, "label": specialty_label(s)} for s in specialties],
        "first_date": bounds["first"],
        "reference_date": db.get_reference_date(),
        "reliable_from": _meta("census_reliable_from"),
        "high_occupancy_pct": HIGH_OCCUPANCY_PCT,
    }


def _validate(service, sub_service, specialty, granularity, start, end) -> tuple[str, str]:
    f = get_filters()
    services = {s["service"]: s for s in f["services"]}
    if granularity not in GRANULARITIES:
        raise ValueError("La vista debe ser diaria o mensual.")
    if specialty and (service or sub_service):
        raise ValueError("Filtre por servicio o por especialidad, no por ambos.")
    if service and service not in services:
        raise ValueError(f"Servicio desconocido: {service}.")
    if sub_service:
        if not service or sub_service not in {s["value"] for s in services[service]["sub_services"]}:
            raise ValueError("El subservicio no pertenece al servicio seleccionado.")
    if specialty and specialty not in {s["value"] for s in f["specialties"]}:
        raise ValueError(f"Especialidad desconocida: {specialty}.")
    bounds = []
    for value, default in ((start, f["first_date"]), (end, f["reference_date"])):
        if value is None:
            bounds.append(default)
            continue
        if not DATE_PATTERN.match(value):
            raise ValueError("Las fechas deben tener formato AAAA-MM-DD.")
        try:
            date.fromisoformat(value)
        except ValueError as e:
            raise ValueError(f"Fecha inválida: {value}.") from e
        bounds.append(value)
    start, end = bounds[0], min(bounds[1], f["reference_date"])   # nunca más allá de "hoy"
    if start > end:
        raise ValueError("La fecha inicial es posterior a la final.")
    return start, end


def get_occupancy(service: str | None = None, sub_service: str | None = None, specialty: str | None = None,
                  granularity: str = "daily", start: str | None = None, end: str | None = None) -> dict:
    """Serie de ocupación según el filtro + resumen + comparación entre servicios + avisos de calidad."""
    start, end = _validate(service, sub_service, specialty, granularity, start, end)

    if specialty:
        daily = _rows("""SELECT census_date AS day, patients AS occupied FROM specialty_census_daily
                         WHERE specialty_group = ? AND census_date BETWEEN ? AND ? ORDER BY day""",
                      (specialty, start, end))
        capacity = None
        scope = {"type": "specialty", "label": f"Pacientes hospitalizados atendidos por {specialty_label(specialty)}"}
    else:
        where, params = ["census_date BETWEEN ? AND ?"], [start, end]
        cap_where, cap_params = ["1 = 1"], []
        for column, value in (("service", service), ("sub_service", sub_service)):
            if value:
                where.append(f"{column} = ?")
                cap_where.append(f"{column} = ?")
                params.append(value)
                cap_params.append(value)
        daily = _rows(f"""SELECT census_date AS day, SUM(occupied_beds) AS occupied,
                                 SUM(census_source = 'estancias') AS from_stays
                          FROM v_occupancy_sub_daily WHERE {' AND '.join(where)}
                          GROUP BY census_date ORDER BY census_date""", tuple(params))
        capacity = _rows(f"""SELECT SUM(capacity_beds) AS total, SUM(physical_beds) AS physical
                             FROM bed_capacity_sub WHERE {' AND '.join(cap_where)}""", tuple(cap_params))[0]
        label = "Todo el hospital" if not service else service + (f" · {sub_label(sub_service)}" if sub_service else "")
        scope = {"type": "beds", "label": label}

    physical = capacity["physical"] if capacity else None
    labels, occupied = _aggregate(daily, granularity)
    return {
        "scope": scope,
        "granularity": granularity,
        "start": start,
        "end": end,
        "labels": labels,
        "occupied": occupied,
        "physical_pct": [pct(v, physical) if physical else None for v in occupied],
        "capacity": {"physical_beds": physical, "total_beds": capacity["total"]} if capacity else None,
        "threshold_beds": round(physical * HIGH_OCCUPANCY_PCT / 100, 1) if physical else None,
        "summary": _summary(daily, physical),
        "by_service": by_service(start, end),
        "monthly_matrix": monthly_matrix(start, end),
        "notes": _notes(service, specialty, start, end, daily),
        "incomplete_from": _incomplete_from(service, specialty, daily, end),
    }


def _incomplete_from(service, specialty, daily, end) -> str | None:
    """Primer día del tramo reciente en que las unidades críticas pueden subcontar (el gráfico lo sombrea).
    Hoy (end) queda fuera: la cama registrada sí es confiable para el día de corte."""
    if specialty or (service and service not in CRITICAL_SERVICES) or not any(r.get("from_stays") for r in daily):
        return None
    first = (date.fromisoformat(end) - timedelta(days=RECENT_UNDERCOUNT_DAYS)).isoformat()
    return first if daily and first > daily[0]["day"] else None


def _aggregate(daily: list[dict], granularity: str) -> tuple[list[str], list[float]]:
    if granularity == "daily":
        return [r["day"] for r in daily], [r["occupied"] for r in daily]
    months: dict[str, list[int]] = {}
    for r in daily:
        months.setdefault(r["day"][:7], []).append(r["occupied"])
    return list(months), [round(sum(v) / len(v), 1) for v in months.values()]


def _summary(daily: list[dict], physical: int | None) -> dict:
    if not daily:
        return {"days": 0}
    values = [r["occupied"] for r in daily]
    peak = max(daily, key=lambda r: r["occupied"])
    low = min(daily, key=lambda r: r["occupied"])
    avg = round(sum(values) / len(values), 1)
    return {
        "days": len(values), "avg": avg, "max": peak["occupied"], "max_date": peak["day"],
        "min": low["occupied"], "min_date": low["day"], "today": daily[-1]["occupied"], "today_date": daily[-1]["day"],
        "avg_physical_pct": pct(avg, physical) if physical else None,
        "days_over_threshold": sum(v >= physical * HIGH_OCCUPANCY_PCT / 100 for v in values) if physical else None,
    }


def by_service(start: str, end: str) -> list[dict]:
    """Promedio diario de camas ocupadas por servicio en el periodo (tabla comparativa)."""
    rows = _rows("""SELECT d.service, ROUND(AVG(d.occ), 1) AS avg_occupied, MAX(d.occ) AS max_occupied,
                           k.physical AS physical_beds, SUM(d.occ >= k.physical * ? / 100.0) AS days_over_threshold
                    FROM (SELECT census_date, service, SUM(occupied_beds) AS occ FROM v_occupancy_sub_daily
                          WHERE census_date BETWEEN ? AND ? GROUP BY census_date, service) d
                    JOIN (SELECT service, SUM(physical_beds) AS physical FROM bed_capacity_sub GROUP BY service) k
                      USING (service)
                    GROUP BY d.service ORDER BY avg_occupied DESC""", (HIGH_OCCUPANCY_PCT, start, end))
    for r in rows:
        r["avg_physical_pct"] = pct(r["avg_occupied"], r["physical_beds"])
    return rows


def monthly_matrix(start: str, end: str) -> dict:
    """Promedio de camas ocupadas por servicio y mes (lo que pide el reto: promedio mensual por servicio)."""
    rows = _rows("""SELECT substr(census_date, 1, 7) AS month, service, ROUND(AVG(occ), 1) AS avg_occupied
                    FROM (SELECT census_date, service, SUM(occupied_beds) AS occ FROM v_occupancy_sub_daily
                          WHERE census_date BETWEEN ? AND ? GROUP BY census_date, service)
                    GROUP BY month, service ORDER BY month""", (start, end))
    months = sorted({r["month"] for r in rows})
    by_key = {(r["service"], r["month"]): r["avg_occupied"] for r in rows}
    services = [s["service"] for s in get_filters()["services"]]
    return {"months": months,
            "rows": [{"service": s, "values": [by_key.get((s, m)) for m in months]} for s in services]}


def _notes(service, specialty, start, end, daily) -> list[str]:
    f = get_filters()
    notes = ["La capacidad es estimada con las camas distintas usadas en el periodo (sin incluir las virtuales)."]
    if start < f["reliable_from"]:
        notes.append("Mayo aparece más bajo de lo real: el extracto no incluye pacientes que ingresaron antes "
                     "del 1 de mayo. Compare a partir de junio.")
    if specialty:
        notes.append("Cuenta pacientes hospitalizados que recibieron al menos un servicio de esta especialidad "
                     "durante su estancia; un paciente puede contar en varias especialidades.")
    elif (not service or service in CRITICAL_SERVICES) and any(r.get("from_stays") for r in daily):
        notes.append("En UCI, Cuidado Intermedio y Básico Neonatal la historia se reconstruye con las estancias "
                     "facturadas, porque cada ingreso solo guarda su última cama. En las últimas "
                     f"{RECENT_UNDERCOUNT_DAYS} jornadas ambas fuentes pueden subcontar; el dato de hoy es el más confiable.")
    if not specialty and (not service or service not in CRITICAL_SERVICES):
        notes.append("El servicio es la cama registrada del ingreso: los traslados internos no se ven.")
    return notes
