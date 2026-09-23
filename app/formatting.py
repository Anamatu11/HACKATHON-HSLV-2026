"""Formato de cifras para textos en español (Colombia): 1.169 y 58,7."""


def fmt_number(value: float, decimals: int = 1) -> str:
    text = f"{value:,.{decimals}f}" if isinstance(value, float) else f"{value:,}"
    return text.replace(",", "X").replace(".", ",").replace("X", ".")


def pct(part: float, total: float) -> float:
    """Porcentaje con un decimal; 0 si el total es 0."""
    return round(100.0 * part / total, 1) if total else 0.0
