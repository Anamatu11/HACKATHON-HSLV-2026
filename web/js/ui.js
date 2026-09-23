// Utilidades de interfaz. Todo texto que viene de la API se inserta con textContent (nunca innerHTML)
// para evitar inyección de HTML.

const numberFmt = new Intl.NumberFormat("es-CO", { maximumFractionDigits: 1 });
const dateFmt = new Intl.DateTimeFormat("es-CO", { day: "numeric", month: "long", year: "numeric", timeZone: "UTC" });

export const fmt = (v) => (typeof v === "number" ? numberFmt.format(v) : v ?? "—");
export const fmtDate = (iso) => dateFmt.format(new Date(`${iso}T00:00:00Z`));

/** Crea un elemento: el("div", {class: "x", onclick: fn}, ["texto", otroNodo]) */
export function el(tag, attrs = {}, children = []) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (value === undefined || value === null || value === false) continue;
    if (key.startsWith("on")) node.addEventListener(key.slice(2), value);
    else if (key === "class") node.className = value;
    else node.setAttribute(key, value === true ? "" : value);
  }
  for (const child of [].concat(children)) {
    if (child === null || child === undefined || child === false) continue;
    node.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return node;
}

export const STATUS_LABEL = { ok: "Normal", warning: "Atención", critical: "Crítico", info: "Informativo" };
const STATUS_ICON = { ok: "✓", warning: "!", critical: "▲", info: "i" };

/** Etiqueta de estado: color + icono + texto (nunca solo color). */
export function statusBadge(status) {
  const cls = status === "info" ? "status status-ok" : `status status-${status}`;
  return el("span", { class: cls }, [el("span", { "aria-hidden": "true" }, STATUS_ICON[status] || "•"),
    STATUS_LABEL[status] || status]);
}

// Nombres legibles para las columnas más comunes del SQL (el SQL usa alias en inglés)
const COLUMN_LABELS = {
  service: "Servicio", admissions: "Ingresos", occupied_beds: "Camas ocupadas", capacity_beds: "Camas totales",
  physical_beds: "Camas físicas", occupancy_pct: "Ocupación %", occupancy_physical_pct: "Ocupación física %",
  item_name: "Medicamento", item_code: "Código", stock_units: "Stock (und)", avg_daily_consumption: "Consumo diario",
  days_of_inventory: "Días de inventario", expiry_date: "Vence", triage_level: "Triage", attentions: "Atenciones",
  avg_wait_min: "Espera promedio (min)", overall_avg_wait_min: "Espera general (min)", specialty: "Especialidad",
  units: "Unidades", month: "Mes", census_date: "Fecha", diagnosis_chapter: "Capítulo CIE-10",
  admission_class: "Clase de ingreso", scheduled: "Programadas", performed: "Realizadas", age_group: "Grupo de edad",
};
export const columnLabel = (c) => COLUMN_LABELS[c] || c.replace(/_/g, " ");

/** Tabla de datos genérica con columnas numéricas alineadas a la derecha. */
export function dataTable(columns, rows, { maxRows } = {}) {
  const shown = maxRows ? rows.slice(0, maxRows) : rows;
  const isNum = columns.map((_, i) => shown.length > 0 && shown.every((r) => r[i] === null || typeof r[i] === "number"));
  return el("table", { class: "data-table w-full text-sm" }, [
    el("thead", {}, el("tr", {}, columns.map((c, i) => el("th", { class: isNum[i] ? "num" : "", scope: "col" }, columnLabel(c))))),
    el("tbody", {}, shown.map((r) => el("tr", {}, r.map((v, i) => el("td", { class: isNum[i] ? "num" : "" }, fmt(v)))))),
  ]);
}
