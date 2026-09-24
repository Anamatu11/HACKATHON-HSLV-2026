"""
Informe PDF de una consulta del asistente IA (exclusivo de Gerencia / Dirección).

Responsable: Rol A.

Se arma SOLO con el registro de la bitácora (app/audit.py): la pregunta, la respuesta, la tabla completa,
la gráfica (dibujada aquí, en vectorial, con reportlab), las recomendaciones, el SQL ejecutado y una sección
de auditoría (quién, cuándo, con qué motor, controles de seguridad, huellas SHA-256 e historial reciente).
"""
import re
from datetime import datetime
from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.graphics.charts.barcharts import HorizontalBarChart
from reportlab.graphics.charts.lineplots import LinePlot
from reportlab.graphics.shapes import Drawing, String
from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas as pdf_canvas
from reportlab.platypus import (Image, KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
                                XPreformatted)

from app import audit, db
from app.formatting import fmt_number

LOGO = Path(__file__).resolve().parent.parent / "web" / "assets" / "logo-hospital.png"
GREEN, GREEN_DARK, NAVY = colors.HexColor("#76b82a"), colors.HexColor("#327531"), colors.HexColor("#29235c")
GRID, MUTED, ZEBRA = colors.HexColor("#e2e8f0"), colors.HexColor("#64748b"), colors.HexColor("#f7f7fa")
SERIES = [colors.HexColor(c) for c in ("#327531", "#2a78d6", "#eb6834", "#4a3aa7")]
MOTTO = "¡Pensando en ti, doy lo mejor de mí!"
MAX_CHART_CATEGORIES = 15
PAGE_W, PAGE_H = A4
MARGIN = 1.8 * cm
CONTENT_W = PAGE_W - 2 * MARGIN

# Mismas etiquetas que el panel (web/js/ui.js) para que tabla y gráfico se lean igual
COLUMN_LABELS = {
    "service": "Servicio", "sub_service": "Subservicio", "admissions": "Ingresos", "occupied_beds": "Camas ocupadas",
    "capacity_beds": "Camas totales", "physical_beds": "Camas físicas", "occupancy_pct": "Ocupación %",
    "occupancy_physical_pct": "Ocupación física %", "item_name": "Medicamento", "item_code": "Código",
    "stock_units": "Stock (und)", "avg_daily_consumption": "Consumo diario", "days_of_inventory": "Días de inventario",
    "expiry_date": "Vence", "triage_level": "Triage", "attentions": "Atenciones", "avg_wait_min": "Espera promedio (min)",
    "overall_avg_wait_min": "Espera general (min)", "specialty": "Especialidad", "units": "Unidades", "month": "Mes",
    "census_date": "Fecha", "diagnosis_chapter": "Capítulo CIE-10", "diagnosis_name": "Diagnóstico",
    "diagnosis_code": "Código CIE-10", "admission_class": "Clase de ingreso", "scheduled": "Programadas",
    "performed": "Realizadas", "age_group": "Grupo de edad",
}
COLUMN_LABELS.update({"fecha_hora": "Fecha y hora", "evento": "Evento", "detalle": "Detalle", "estado": "Estado"})
EVENT_LABELS = {"query": "Consulta", "report": "Informe PDF"}
ROLE_LABELS = {"director": "Gerencia / Dirección", "service_head": "Jefe de servicio"}
# Capítulos CIE-10 (misma lectura que el listado de admisiones del panel)
CHAPTERS = {
    "A": "Infecciosas", "B": "Infecciosas", "C": "Oncológicas", "D": "Hematológicas", "E": "Endocrinas",
    "F": "Salud mental", "G": "Neurológicas", "H": "Ojo y oído", "I": "Cardiovasculares", "J": "Respiratorias",
    "K": "Digestivas", "L": "Piel", "M": "Osteomusculares", "N": "Genitourinarias", "O": "Embarazo y parto",
    "P": "Perinatales", "Q": "Malformaciones", "R": "Síntomas generales", "S": "Traumatismos",
    "T": "Traumatismos e intoxicaciones", "Z": "Controles y otros",
}


def _cell(column: str, value) -> str:
    """Valor de celda/categoría legible: el capítulo CIE-10 'S' se muestra 'S · Traumatismos'."""
    if column == "diagnosis_chapter" and value in CHAPTERS:
        return f"{value} · {CHAPTERS[value]}"
    return _fmt(value)


def column_label(column: str) -> str:
    return COLUMN_LABELS.get(column, column.replace("_", " ").capitalize())


def _fmt(value) -> str:
    if value is None:
        return "—"
    if isinstance(value, bool):
        return "Sí" if value else "No"
    if isinstance(value, (int, float)):
        return fmt_number(value)
    return str(value)


def _fmt_ts(iso: str) -> str:
    """'2026-09-24T10:05:31-05:00' -> '24/09/2026 10:05:31 (hora Colombia)'."""
    try:
        return datetime.fromisoformat(iso).strftime("%d/%m/%Y %H:%M:%S") + " (hora Colombia)"
    except (TypeError, ValueError):
        return str(iso)


def _rich(text: str) -> str:
    """Texto del LLM -> marcado de Paragraph: escapa HTML y convierte **negrita**."""
    safe = escape(text or "")
    safe = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", safe)
    return safe.replace("\n\n", "<br/><br/>").replace("\n", "<br/>")


# --- Estilos -------------------------------------------------------------------------

def _styles() -> dict:
    base = getSampleStyleSheet()
    body = ParagraphStyle("body", parent=base["BodyText"], fontName="Helvetica", fontSize=9.5, leading=13.5)
    return {
        "title": ParagraphStyle("title", parent=body, fontName="Helvetica-Bold", fontSize=16, leading=20, textColor=NAVY),
        "subtitle": ParagraphStyle("subtitle", parent=body, fontSize=9, textColor=MUTED),
        "h2": ParagraphStyle("h2", parent=body, fontName="Helvetica-Bold", fontSize=11.5, leading=15, textColor=NAVY,
                             spaceBefore=12, spaceAfter=5),
        "body": body,
        "answer": ParagraphStyle("answer", parent=body, fontSize=10.5, leading=15),
        "small": ParagraphStyle("small", parent=body, fontSize=8, leading=10.5),
        "small_right": ParagraphStyle("small_right", parent=body, fontSize=8, leading=10.5, alignment=TA_RIGHT),
        "head": ParagraphStyle("head", parent=body, fontName="Helvetica-Bold", fontSize=8, leading=10.5,
                               textColor=colors.white),
        "head_right": ParagraphStyle("head_right", parent=body, fontName="Helvetica-Bold", fontSize=8, leading=10.5,
                                     textColor=colors.white, alignment=TA_RIGHT),
        "label": ParagraphStyle("label", parent=body, fontName="Helvetica-Bold", fontSize=8.5, leading=11,
                                textColor=MUTED),
        "value": ParagraphStyle("value", parent=body, fontSize=8.5, leading=11),
        "code": ParagraphStyle("code", parent=body, fontName="Courier", fontSize=7.8, leading=10),
    }


def _key_value_table(pairs: list[tuple[str, str]], st: dict) -> Table:
    data = [[Paragraph(escape(k), st["label"]), Paragraph(v, st["value"])] for k, v in pairs]
    table = Table(data, colWidths=[4.6 * cm, CONTENT_W - 4.6 * cm])
    table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LINEBELOW", (0, 0), (-1, -1), 0.4, GRID),
        ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    return table


def _data_table(columns: list[str], rows: list[list], st: dict) -> Table:
    numeric = [bool(rows) and all(r[i] is None or isinstance(r[i], (int, float)) for r in rows)
               for i in range(len(columns))]
    header = [Paragraph(escape(column_label(c)), st["head_right"] if numeric[i] else st["head"])
              for i, c in enumerate(columns)]
    body = [[Paragraph(escape(_cell(columns[i], v)), st["small_right"] if numeric[i] else st["small"])
             for i, v in enumerate(r)] for r in rows]
    # Columnas de texto más anchas que las numéricas
    weights = [1.0 if n else 2.4 for n in numeric]
    widths = [CONTENT_W * w / sum(weights) for w in weights]
    table = Table([header, *body], colWidths=widths, repeatRows=1)
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), GREEN_DARK),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LINEBELOW", (0, 0), (-1, -1), 0.3, GRID),
        ("TOPPADDING", (0, 0), (-1, -1), 2.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
    ]
    style += [("BACKGROUND", (0, i), (-1, i), ZEBRA) for i in range(2, len(rows) + 1, 2)]
    table.setStyle(TableStyle(style))
    return table


# --- Gráfico -------------------------------------------------------------------------

def _chart(record: dict) -> Drawing | None:
    """Gráfico del informe según el `chart` que eligió el agente (line / bar). None si no aplica."""
    chart, columns, rows = record.get("chart") or {}, record.get("columns", []), record.get("rows", [])
    if chart.get("type") in (None, "none") or len(rows) < 2:
        return None
    try:
        xi, yi = columns.index(chart["x"]), columns.index(chart["y"])
    except (KeyError, ValueError):
        return None
    points = [(_cell(chart["x"], r[xi]), float(r[yi])) for r in rows if isinstance(r[yi], (int, float))]
    if len(points) < 2:
        return None
    return _line_chart(points, chart["y"]) if chart["type"] == "line" else _bar_chart(points, chart["y"])


def _bar_chart(points: list[tuple[str, float]], y_column: str) -> Drawing:
    shown = points[:MAX_CHART_CATEGORIES]
    names = [(label[:42] + "…") if len(label) > 43 else label for label, _ in reversed(shown)]
    label_w = max(stringWidth(n, "Helvetica", 7) for n in names) + 10
    height = 16 * len(shown)
    drawing = Drawing(CONTENT_W, height + 40)
    bars = HorizontalBarChart()
    bars.x, bars.y, bars.width, bars.height = label_w, 14, CONTENT_W - label_w - 30, height
    bars.data = [[v for _, v in reversed(shown)]]
    bars.categoryAxis.categoryNames = names
    bars.categoryAxis.labels.fontName, bars.categoryAxis.labels.fontSize = "Helvetica", 7
    bars.categoryAxis.labels.boxAnchor = "e"
    bars.categoryAxis.strokeColor = GRID
    bars.valueAxis.valueMin = 0
    bars.valueAxis.labels.fontName, bars.valueAxis.labels.fontSize = "Helvetica", 7
    bars.valueAxis.labelTextFormat = lambda v: fmt_number(v, 0) if float(v).is_integer() else fmt_number(v)
    bars.valueAxis.strokeColor, bars.valueAxis.gridStrokeColor, bars.valueAxis.visibleGrid = GRID, GRID, True
    bars.bars[0].fillColor, bars.bars[0].strokeColor = SERIES[0], None
    bars.barLabelFormat = lambda v: fmt_number(v, 0) if float(v).is_integer() else fmt_number(v)
    bars.barLabels.fontName, bars.barLabels.fontSize, bars.barLabels.boxAnchor = "Helvetica", 6.5, "w"
    bars.barLabels.dx = 3
    drawing.add(bars)
    top = bars.y + height + 12
    drawing.add(String(bars.x, top, column_label(y_column), fontName="Helvetica-Bold", fontSize=7.5, fillColor=MUTED))
    if len(points) > len(shown):
        drawing.add(String(CONTENT_W, top, f"Se muestran las primeras {len(shown)} de {len(points)} categorías "
                           "(la tabla trae todas)", fontName="Helvetica", fontSize=6.5, fillColor=MUTED,
                           textAnchor="end"))
    return drawing


def _line_chart(points: list[tuple[str, float]], y_column: str) -> Drawing:
    drawing = Drawing(CONTENT_W, 7 * cm)
    plot = LinePlot()
    plot.x, plot.y, plot.width, plot.height = 1.3 * cm, 1.2 * cm, CONTENT_W - 1.8 * cm, 5.2 * cm
    plot.data = [[(i, v) for i, (_, v) in enumerate(points)]]
    plot.lines[0].strokeColor, plot.lines[0].strokeWidth = SERIES[0], 1.8
    plot.xValueAxis.valueMin, plot.xValueAxis.valueMax = 0, len(points) - 1
    step = max(1, len(points) // 8)
    plot.xValueAxis.valueSteps = list(range(0, len(points), step))
    plot.xValueAxis.labelTextFormat = lambda i: points[int(i)][0][:10] if 0 <= int(i) < len(points) else ""
    plot.yValueAxis.valueMin = 0
    for axis in (plot.xValueAxis, plot.yValueAxis):
        axis.labels.fontName, axis.labels.fontSize, axis.strokeColor = "Helvetica", 7, GRID
    plot.yValueAxis.visibleGrid, plot.yValueAxis.gridStrokeColor = True, GRID
    plot.yValueAxis.labelTextFormat = lambda v: fmt_number(v, 0) if float(v).is_integer() else fmt_number(v)
    drawing.add(plot)
    drawing.add(String(plot.x, 6.6 * cm, column_label(y_column), fontName="Helvetica", fontSize=7, fillColor=MUTED))
    return drawing


# --- Pie de página con "Página X de Y" -----------------------------------------------

class _NumberedCanvas(pdf_canvas.Canvas):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._pages = []

    def showPage(self):
        self._pages.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        total = len(self._pages)
        for state in self._pages:
            self.__dict__.update(state)
            self._draw_footer(total)
            super().showPage()
        super().save()

    def _draw_footer(self, total: int):
        width = (PAGE_W - 2 * MARGIN) / 3
        for i, color in enumerate((GREEN, GREEN_DARK, NAVY)):       # franja de marca
            self.setFillColor(color)
            self.rect(MARGIN + i * width, 1.35 * cm, width, 2.2, stroke=0, fill=1)
        self.setFont("Helvetica", 7)
        self.setFillColor(MUTED)
        self.drawString(MARGIN, 0.95 * cm, "HSLV · Asistente IA de gestión hospitalaria · Documento confidencial, uso interno")
        self.drawRightString(PAGE_W - MARGIN, 0.95 * cm, f"Página {self._pageNumber} de {total}")


# --- Informe -------------------------------------------------------------------------

def _limitations(record: dict) -> list[str]:
    sql = (record.get("sql") or "").lower()
    notes = []
    if "drug_inventory" in sql:
        notes.append("El inventario de medicamentos es SIMULADO a partir del consumo real de los últimos 30 días.")
    if "occupancy" in sql or "capacity" in sql:
        notes.append("La capacidad de camas es ESTIMADA a partir de las camas distintas observadas.")
    if "diagnosis_" in sql:
        notes.append("El diagnóstico específico se entrega solo en cifras agregadas; nunca por paciente.")
    notes.append("Servicio del ingreso = cama registrada; los traslados internos no se ven.")
    notes.append("Datos de mayo a septiembre de 2026; septiembre llega hasta la fecha de corte.")
    return notes


def build_pdf(record: dict, requested_by: dict) -> bytes:
    """PDF del registro `record` (consulta de la bitácora). `requested_by` = usuario que descarga."""
    st = _styles()
    generated_at = audit.now_iso()
    reference_date = db.get_reference_date()
    columns, rows = record.get("columns", []), record.get("rows", [])
    fingerprint_ok = audit.result_fingerprint(columns, rows) == record.get("result_sha256")
    chain_ok, chain_count = audit.verify_chain()

    story = []
    # Encabezado: el logo siempre sobre blanco y sin alterar (Manual de Marca)
    if LOGO.exists():
        logo = Image(str(LOGO))
        logo.drawHeight, logo.drawWidth = 1.5 * cm, 1.5 * cm * logo.imageWidth / logo.imageHeight
        header = Table([[logo, [Paragraph("Informe de consulta · Asistente IA", st["title"]),
                                Paragraph(f"Hospital Susana López de Valencia E.S.E. · {escape(MOTTO)}", st["subtitle"])]]],
                       colWidths=[logo.drawWidth + 0.4 * cm, None])
        header.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
        story.append(header)
    else:
        story.append(Paragraph("Informe de consulta · Asistente IA", st["title"]))
    story.append(Spacer(1, 8))

    story.append(_key_value_table([
        ("Pregunta", f"<b>{escape(record.get('question', ''))}</b>"),
        ("Consultado por", escape(f"{record.get('name')} ({record.get('username')}) · "
                                  f"{ROLE_LABELS.get(record.get('role'), record.get('role'))}")),
        ("Fecha de la consulta", escape(_fmt_ts(record.get("at")))),
        ("Datos con corte al", escape(reference_date)),
        ("Origen de la respuesta", escape(record.get("engine", ""))),
    ], st))

    story.append(Paragraph("1. Respuesta", st["h2"]))
    story.append(Paragraph(_rich(record.get("answer", "")), st["answer"]))

    drawing = _chart(record)
    if drawing is not None:
        story.append(KeepTogether([Paragraph("2. Gráfico", st["h2"]), drawing]))

    story.append(Paragraph(f"{3 if drawing else 2}. Resultados ({fmt_number(len(rows))} "
                           f"fila{'s' if len(rows) != 1 else ''})", st["h2"]))
    story.append(_data_table(columns, rows, st) if rows else Paragraph("La consulta no devolvió filas.", st["body"]))

    n = 4 if drawing else 3
    if record.get("recommendations"):
        story.append(Paragraph(f"{n}. Recomendaciones", st["h2"]))
        story.extend(Paragraph(f"• {_rich(r)}", st["body"]) for r in record["recommendations"])
        n += 1

    story.append(KeepTogether([
        Paragraph(f"{n}. Consulta SQL ejecutada", st["h2"]),
        XPreformatted(escape(record.get("sql") or "(sin consulta SQL)"), st["code"]),
    ]))
    n += 1

    # --- Auditoría ---
    story.append(Paragraph(f"{n}. Auditoría y trazabilidad", st["h2"]))
    controls = ("Solo lectura: una única sentencia SELECT/WITH; operaciones de escritura bloqueadas. "
                "Base de datos abierta en modo solo lectura con tiempo máximo por consulta. "
                "Sin columnas personales (paciente, fecha de nacimiento, cama). "
                "Diagnóstico específico solo en cifras agregadas. Máximo 200 filas.")
    story.append(_key_value_table([
        ("ID de la consulta", f"<font face='Courier'>{escape(record.get('id', ''))}</font>"),
        ("Usuario / rol", escape(f"{record.get('name')} ({record.get('username')}) · "
                                 f"{ROLE_LABELS.get(record.get('role'), record.get('role'))}")),
        ("Fecha de la consulta", escape(_fmt_ts(record.get("at")))),
        ("Informe generado", escape(f"{_fmt_ts(generated_at)} por {requested_by.get('name')} "
                                    f"({requested_by.get('username')})")),
        ("Motor de respuesta", escape(record.get("engine", ""))),
        ("Controles de seguridad", escape(controls)),
        ("Validación del SQL", "Aprobada por el validador de seguridad (sql_guard) antes de ejecutarse"),
        ("Filas devueltas", fmt_number(record.get("row_count", len(rows)))),
        ("Huella del resultado (SHA-256)",
         f"<font face='Courier' size='7'>{escape(record.get('result_sha256', ''))}</font><br/>"
         + ("Verificada: la tabla de este informe coincide con la consultada."
            if fingerprint_ok else "<font color='#d03b3b'><b>NO coincide: el resultado fue alterado.</b></font>")),
        ("Registro en bitácora",
         f"<font face='Courier' size='7'>{escape(record.get('hash', ''))}</font><br/>"
         + (f"Bitácora íntegra ({fmt_number(chain_count)} registros encadenados)."
            if chain_ok else "<font color='#d03b3b'><b>ALERTA: la bitácora fue modificada.</b></font>")),
        ("Limitaciones de los datos", "<br/>".join(f"• {escape(x)}" for x in _limitations(record))),
    ], st))

    history = audit.recent_events(record.get("username", ""), limit=10)
    if history:
        story.append(Paragraph("Actividad reciente del usuario", st["h2"]))
        story.append(_data_table(
            ["fecha_hora", "evento", "detalle", "estado"],
            [[_fmt_ts(h["at"]).replace(" (hora Colombia)", ""), EVENT_LABELS.get(h["event"], h["event"]),
              h.get("question") or f"Informe de la consulta {h.get('query_id')}",
              "Respondida" if h.get("status") == "ok" and h["event"] == "query"
              else "Descargado" if h["event"] == "report" else f"Rechazada: {h.get('error') or ''}"]
             for h in history], st))

    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=MARGIN, rightMargin=MARGIN, topMargin=MARGIN,
                            bottomMargin=2 * cm, title=f"Informe HSLV · {record.get('question', '')[:80]}",
                            author=f"{requested_by.get('name')} · Asistente IA HSLV", subject="Informe de consulta")
    doc.build(story, canvasmaker=_NumberedCanvas)
    return buffer.getvalue()


def filename_for(record: dict) -> str:
    stamp = re.sub(r"[^0-9]", "", (record.get("at") or "")[:16])
    return f"informe_HSLV_{stamp}_{record.get('id', 'consulta')}.pdf"
