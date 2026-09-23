"""
Reglas de alertas y recomendaciones -> GET /api/alerts y campo `recommendations` del chat.

Responsable: Rol B.

Reglas simples y explicables (CLAUDE.md §6). Cada alerta:
    {"type": "stock|expiry|occupancy|wait_time|surgery|forecast",
     "severity": "critical|warning|info", "title": str, "detail": str}
"""

# Umbrales (ajustar aquí, no dispersos por el código)
STOCK_WARNING_DAYS = 5
STOCK_CRITICAL_DAYS = 2
EXPIRY_WINDOW_DAYS = 30
OCCUPANCY_HIGH_PCT = 90      # sobre camas físicas
OCCUPANCY_LOW_PCT = 60       # servicios de donde se puede reasignar
TRIAGE2_MAX_WAIT_MIN = 30
TRIAGE3_OVER_AVG_PCT = 20    # % sobre su promedio histórico
DAY_SHIFT = (7, 19)          # turno día 07-19; noche 19-07 (causa raíz)


def get_alerts() -> list[dict]:
    """Todas las alertas activas a la fecha REF, ordenadas por severidad."""
    raise NotImplementedError


def stock_alerts() -> list[dict]:
    """days_of_inventory < 5 -> 'Reabastecer X: quedan N días (consumo diario Y)'. Crítico si < 2."""
    raise NotImplementedError


def expiry_alerts() -> list[dict]:
    """expiry_date en <= 30 días con stock alto -> 'Priorizar uso / redistribuir'."""
    raise NotImplementedError


def occupancy_alerts() -> list[dict]:
    """occupancy_physical_pct >= 90 -> abrir camas / reasignar personal; sugerir servicios < 60%."""
    raise NotImplementedError


def wait_time_alerts() -> list[dict]:
    """Triage 2 > 30 min o triage 3 > promedio +20% -> alerta con causa raíz (turno y triage_area)."""
    raise NotImplementedError


def surgery_alerts() -> list[dict]:
    """% no realizadas por especialidad; ingresos con > 1 programación = reprogramaciones."""
    raise NotImplementedError


def recommendations_for(question: str, columns: list[str], rows: list[list]) -> list[str]:
    """Recomendaciones para una respuesta del chat según el tema detectado (stock, ocupación, espera...)."""
    raise NotImplementedError
