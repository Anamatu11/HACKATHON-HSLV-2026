"""
Consultas del dashboard -> GET /api/kpis.

Responsable: Rol B.

La forma del JSON la define el mockData de web/app.js (fuente de verdad del contrato).
Referencia inicial en docs/01-arquitectura.md §3 y SQL de referencia en CLAUDE.md §4.
Usar siempre REF = (SELECT value FROM dataset_meta WHERE key='reference_date').
"""

REF = "(SELECT value FROM dataset_meta WHERE key='reference_date')"


def get_kpis() -> dict:
    """Arma la respuesta completa del dashboard.

    Estructura esperada:
        {
          "reference_date": "2026-09-21",
          "cards": [...4 tarjetas...],
          "series": {"occupancy_daily", "surgery", "admissions_by_service", "top_medications"},
          "medications_table": [...]
        }
    """
    raise NotImplementedError


# --- Tarjetas -------------------------------------------------------------------

def occupancy_today() -> dict:
    """Ocupación hoy (v_occupancy_daily en census_date = REF). Esperado UCI: 27/46 = 58,7%."""
    raise NotImplementedError


def avg_wait_last_week() -> dict:
    """Espera promedio en urgencias últimos 7 días (wait_times). Esperado: 58,6 min, 888 atenciones."""
    raise NotImplementedError


def critical_stock_count() -> dict:
    """Medicamentos con days_of_inventory < 5 (drug_inventory, SIMULADO). Esperado: 35."""
    raise NotImplementedError


def surgery_performance() -> dict:
    """% cirugías realizadas vs programadas (surgery_schedule WHERE in_dataset = 1, was_billed = 1)."""
    raise NotImplementedError


# --- Series para gráficos ---------------------------------------------------------

def occupancy_daily_series(service: str = "UCI", days: int = 30) -> dict:
    """Serie diaria de ocupación (gráfico de línea)."""
    raise NotImplementedError


def surgery_series() -> dict:
    """Programadas vs realizadas (gráfico de quirófanos)."""
    raise NotImplementedError


def admissions_by_service_series() -> dict:
    """Ingresos del mes de REF por servicio. Esperado: Urgencias 1.169, Pediatría 409, Hosp. Adultos 401."""
    raise NotImplementedError


def top_medications_series(limit: int = 10) -> dict:
    """Medicamentos de mayor rotación del mes (medications, item_type = 'Medicamento')."""
    raise NotImplementedError


def medications_table() -> list[dict]:
    """Filas de drug_inventory para la tabla con buscador (el filtro se hace en el navegador)."""
    raise NotImplementedError
