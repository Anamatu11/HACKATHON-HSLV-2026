// Pestaña Ocupación: filtro por servicio/subservicio o especialidad y periodo, camas ocupadas o
// % de camas físicas, gráfico de barras por estado, resumen, avisos de calidad y tablas comparativas.
import { getOccupancy, getOccupancyFilters } from "./api.js";
import { barChart, chartCard, SERIES } from "./charts.js";
import { el, fmt, fmtDate } from "./ui.js";

const $ = (id) => document.getElementById(id);
const monthFmt = new Intl.DateTimeFormat("es-CO", { month: "short", year: "2-digit", timeZone: "UTC" });
const fmtMonth = (ym) => monthFmt.format(new Date(`${ym}-01T00:00:00Z`));

let filters = null;
let requestId = 0;

export async function initOccupancy() {
  try {
    filters = await getOccupancyFilters();
  } catch (e) {
    return showError(e.message);
  }
  fillSelect($("occ-service"), [{ value: "", label: "Todo el hospital" },
    ...filters.services.map((s) => ({ value: s.service, label: `${s.service} (${s.physical_beds} camas físicas)` }))]);
  fillSelect($("occ-specialty"), filters.specialties);
  updateSubServices();
  for (const input of [$("occ-start"), $("occ-end")]) {   // solo días con datos
    input.min = filters.first_date;
    input.max = filters.reference_date;
  }
  // Por defecto: desde el primer mes con datos completos (mayo subcuenta) hasta hoy
  $("occ-start").value = filters.reliable_from;
  $("occ-end").value = filters.reference_date;

  $("occ-filters").addEventListener("change", (e) => {
    if (e.target.id === "occ-service") updateSubServices();
    if (e.target.name === "mode") updateMode();
    if (validDates()) load();
  });
  load();
}

function validDates() {
  const start = $("occ-start");
  const end = $("occ-end");
  let message = "";
  if (!start.value || !end.value) message = "Elija la fecha inicial y la final.";
  else if (start.value < filters.first_date || end.value > filters.reference_date) {
    message = `Hay datos del ${fmtDate(filters.first_date)} al ${fmtDate(filters.reference_date)}.`;
  } else if (start.value > end.value) message = "La fecha «Desde» debe ser anterior o igual a «Hasta».";
  start.setAttribute("aria-invalid", String(Boolean(message)));
  end.setAttribute("aria-invalid", String(Boolean(message)));
  if (message) showError(message);
  else $("occ-error").classList.add("hidden");
  return !message;
}

function fillSelect(select, options) {
  select.replaceChildren(...options.map((o) => el("option", { value: o.value }, o.label)));
}

function updateSubServices() {
  const service = filters.services.find((s) => s.service === $("occ-service").value);
  const subs = service?.sub_services || [];
  fillSelect($("occ-sub"), [{ value: "", label: subs.length > 1 ? "Todos" : "—" },
    ...(subs.length > 1 ? subs.map((s) => ({ value: s.value, label: `${s.label} (${s.physical_beds} camas)` })) : [])]);
  $("occ-sub").disabled = subs.length <= 1;
}

function updateMode() {
  const bySpecialty = mode() === "specialty";
  $("occ-service-box").classList.toggle("hidden", bySpecialty);
  $("occ-sub-box").classList.toggle("hidden", bySpecialty);
  $("occ-specialty-box").classList.toggle("hidden", !bySpecialty);
  // Una especialidad no tiene camas propias: no hay % de ocupación
  document.querySelectorAll('input[name="metric"]').forEach((i) => { i.disabled = bySpecialty; });
  if (bySpecialty) document.querySelector('input[name="metric"][value="beds"]').checked = true;
}

const radio = (name) => document.querySelector(`input[name="${name}"]:checked`).value;
const mode = () => radio("mode");

const period = () => ({ start: $("occ-start").value, end: $("occ-end").value });

async function load() {
  const params = { granularity: "daily", ...period() };   // el promedio mensual se ve en la tabla
  if (mode() === "specialty") params.specialty = $("occ-specialty").value;
  else Object.assign(params, { service: $("occ-service").value, sub_service: $("occ-sub").value });

  const id = ++requestId;
  $("occ-main").style.opacity = "0.5";   // mantiene el render anterior mientras llega el nuevo
  try {
    const data = await getOccupancy(params);
    if (id !== requestId) return;          // llegó una respuesta más nueva
    $("occ-error").classList.add("hidden");
    render(data, radio("metric"));
  } catch (e) {
    showError(e.message);
  } finally {
    if (id === requestId) $("occ-main").style.opacity = "1";
  }
}

function showError(message) {
  $("occ-error").textContent = message;
  $("occ-error").classList.remove("hidden");
}

function render(d, metric) {
  renderSummary(d);
  renderMainChart(d, metric);
  $("occ-notes").replaceChildren(
    el("p", { class: "font-semibold text-slate-700" }, "Cómo leer estos datos"),
    ...d.notes.map((n) => el("p", {}, [el("span", { "aria-hidden": "true", class: "mr-1" }, "ℹ"), n])));
  renderByService(d.by_service);
  renderMatrix(d.monthly_matrix);
}

function tile(label, value, detail) {
  return el("article", { class: "card p-4" }, [
    el("p", { class: "text-xs text-slate-500" }, label),
    el("p", { class: "font-display text-2xl font-semibold mt-1", style: "color: var(--brand-navy)" }, value),
    el("p", { class: "text-xs text-slate-500 mt-1" }, detail),
  ]);
}

function renderSummary(d) {
  const s = d.summary;
  if (!s.days) return $("occ-summary").replaceChildren(tile("Sin datos", "—", "Pruebe otro periodo"));
  const unit = d.scope.type === "specialty" ? "pacientes" : "camas";
  const physical = d.capacity?.physical_beds;
  $("occ-summary").replaceChildren(
    tile("Promedio diario", `${fmt(s.avg)} ${unit}`,
         physical ? `${fmt(s.avg_physical_pct)}% de ${fmt(physical)} camas físicas` : `${fmt(s.days)} días analizados`),
    tile("Pico del periodo", `${fmt(s.max)} ${unit}`, fmtDate(s.max_date)),
    tile(s.today_date === filters.reference_date ? "Hoy" : "Último día del periodo",
         `${fmt(s.today)} ${unit}`, fmtDate(s.today_date)),
    physical
      ? tile(`Días con ocupación ≥ ${filters.high_occupancy_pct}%`, `${fmt(s.days_over_threshold)} de ${fmt(s.days)}`,
             `${fmt(Math.round((100 * s.days_over_threshold) / s.days))}% de los días`)
      : tile("Mínimo del periodo", `${fmt(s.min)} ${unit}`, fmtDate(s.min_date)),
  );
}

// --- Gráfico principal: barras por día/semana/mes coloreadas por estado ---------------------

const DAILY_MAX_DAYS = 31;     // hasta un mes: una barra por día
const WEEKLY_MAX_DAYS = 120;   // hasta ~4 meses: una barra por semana; más: una por mes
const dayFmt = new Intl.DateTimeFormat("es-CO", { day: "numeric", month: "short", timeZone: "UTC" });
const fmtDay = (iso) => dayFmt.format(new Date(`${iso}T00:00:00Z`)).replace(".", "");

// Estado de cada barra según % de camas físicas (color + texto en la leyenda y el tooltip)
const STATUS = {
  ok: { label: "Normal (menos de 90%)", color: cssVar("--bar-ok") },
  high: { label: "Alta (90% a 100%)", color: cssVar("--bar-high") },
  over: { label: "Sobre la capacidad (más de 100%)", color: cssVar("--bar-over") },
  incomplete: { label: "Datos incompletos", color: cssVar("--bar-incomplete") },
  neutral: { label: "Pacientes", color: SERIES[0] },
};

function cssVar(name) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

/** Agrupa la serie diaria en barras. Devuelve [{label, from, to, avg, days, incomplete}]. */
function bucketize(d) {
  const days = d.labels.map((day, i) => ({ day, value: d.occupied[i] }));
  const unit = days.length <= DAILY_MAX_DAYS ? "day" : days.length <= WEEKLY_MAX_DAYS ? "week" : "month";
  const groups = [];
  days.forEach((p, i) => {
    const key = unit === "day" ? p.day : unit === "week" ? Math.floor(i / 7) : p.day.slice(0, 7);
    if (!groups.length || groups[groups.length - 1].key !== key) groups.push({ key, points: [] });
    groups[groups.length - 1].points.push(p);
  });
  // Los días del tramo incompleto (antes de hoy) marcan la barra; hoy sí es confiable
  const isIncomplete = (day) => d.incomplete_from && day >= d.incomplete_from && day < d.end;
  return {
    unit,
    bars: groups.map(({ points }) => {
      const from = points[0].day;
      const to = points[points.length - 1].day;
      return {
        from, to, days: points.length,
        avg: Math.round((10 * points.reduce((s, p) => s + p.value, 0)) / points.length) / 10,
        incomplete: points.some((p) => isIncomplete(p.day)),
        label: unit === "day" || from === to ? fmtDay(from) : unit === "month" ? fmtMonth(from.slice(0, 7))
          : from.slice(5, 7) === to.slice(5, 7) ? `${Number(from.slice(8))}–${fmtDay(to)}` : `${fmtDay(from)}–${fmtDay(to)}`,
      };
    }),
  };
}

function barStatus(bar, physical) {
  if (!physical) return "neutral";
  if (bar.incomplete) return "incomplete";
  const pctValue = (100 * bar.avg) / physical;
  return pctValue > 100 ? "over" : pctValue >= filters.high_occupancy_pct ? "high" : "ok";
}

const UNIT_WORDS = { day: ["día", "días"], week: ["semana", "semanas"], month: ["mes", "meses"] };

function renderMainChart(d, metric) {
  const box = $("occ-main");
  box.replaceChildren();
  const physical = d.capacity?.physical_beds;
  const pctMode = metric === "pct" && physical;
  const { unit, bars } = bucketize(d);
  const statuses = bars.map((b) => barStatus(b, physical));
  const values = bars.map((b) => (pctMode ? Math.round((1000 * b.avg) / physical) / 10 : b.avg));
  const [one, many] = UNIT_WORDS[unit];
  const what = d.scope.type === "specialty" ? "pacientes" : "camas ocupadas";

  const canvas = chartCard(box, {
    title: `${d.scope.label} · ${pctMode ? "% de camas físicas ocupadas" : `${what} por ${one}`}`,
    subtitle: `${fmtDate(d.start)} – ${fmtDate(d.end)}` + (unit === "day" ? "" : ` · cada barra es el promedio diario del ${one}`),
    tall: true,
  });
  // Resumen en una frase + leyenda en texto, entre el título y el gráfico
  const chartBox = canvas.parentElement;
  chartBox.before(headline(d, bars, statuses, many), legendRow(statuses, physical, pctMode));

  barChart(canvas, {
    labels: bars.map((b) => b.label),
    datasets: [{ label: pctMode ? "% de camas físicas" : `Promedio de ${what}`, data: values,
                 color: statuses.map((s) => STATUS[s].color) }],
    unit: pctMode ? "%" : "",
    maxBarThickness: 48,
    threshold: physical ? { value: pctMode ? 100 : physical, color: cssVar("--brand-navy"), solid: true,
                            label: pctMode ? "Capacidad (100%)" : `Capacidad: ${fmt(physical)} camas físicas` } : undefined,
    tooltipAfter: (i) => {
      const b = bars[i];
      const lines = [b.days > 1 ? `${fmtDate(b.from)} al ${fmtDate(b.to)} (${b.days} días)` : fmtDate(b.from)];
      if (physical) lines.push(`${fmt(Math.round((1000 * b.avg) / physical) / 10)}% de ${fmt(physical)} camas físicas`);
      if (statuses[i] !== "neutral") lines.push(`Estado: ${STATUS[statuses[i]].label}`);
      return lines;
    },
  });
}

function headline(d, bars, statuses, unitPlural) {
  const s = d.summary;
  const physical = d.capacity?.physical_beds;
  let text;
  if (!physical) {
    text = `En promedio, ${fmt(s.avg)} pacientes hospitalizados por día. El pico fue de ${fmt(s.max)} el ${fmtDate(s.max_date)}.`;
  } else {
    const complete = statuses.filter((st) => st !== "incomplete").length;
    const over = statuses.filter((st) => st === "over").length;
    const high = statuses.filter((st) => st === "high").length;
    text = `En promedio, ${fmt(s.avg)} camas ocupadas por día (${fmt(s.avg_physical_pct)}% de las ${fmt(physical)} camas físicas). `
      + (over ? `${fmt(over)} de ${fmt(complete)} ${unitPlural} estuvieron por encima de la capacidad`
              : `Ningún periodo superó la capacidad`)
      + (high ? ` y ${fmt(high)} en ocupación alta.` : ".");
  }
  return el("p", { class: "text-sm mb-2", style: "color: var(--text-primary)" }, text);
}

function legendRow(statuses, physical, pctMode) {
  const present = ["ok", "high", "over", "incomplete", "neutral"].filter((k) => statuses.includes(k));
  const items = present.map((k) => el("span", { class: "inline-flex items-center gap-1.5" }, [
    el("span", { class: "inline-block w-3 h-3 rounded-sm", style: `background: ${STATUS[k].color}`, "aria-hidden": "true" }),
    STATUS[k].label]));
  if (physical) {
    items.push(el("span", { class: "inline-flex items-center gap-1.5" }, [
      el("span", { class: "inline-block w-4 border-t-2", style: "border-color: var(--brand-navy)", "aria-hidden": "true" }),
      pctMode ? "Capacidad (100%)" : "Capacidad (camas físicas)"]));
  }
  return el("div", { class: "flex flex-wrap gap-x-4 gap-y-1 text-xs text-slate-600 mb-2" }, items);
}

function renderByService(rows) {
  const current = $("occ-service").value;
  $("occ-by-service").replaceChildren(el("table", { class: "data-table w-full text-sm" }, [
    el("thead", {}, el("tr", {}, [
      el("th", { scope: "col" }, "Servicio"), el("th", { scope: "col", class: "num" }, "Camas/día"),
      el("th", { scope: "col", class: "num" }, "Camas físicas"), el("th", { scope: "col", class: "num" }, "% físico"),
      el("th", { scope: "col", class: "num" }, `Días ≥ ${filters.high_occupancy_pct}%`),
    ])),
    el("tbody", {}, rows.map((r) => el("tr", { class: r.service === current ? "bg-green-50" : "" }, [
      el("td", {}, el("button", {
        type: "button", class: "underline decoration-dotted text-left", style: "color: var(--brand-navy)",
        onclick: () => selectService(r.service),
      }, r.service)),
      el("td", { class: "num" }, fmt(r.avg_occupied)),
      el("td", { class: "num" }, fmt(r.physical_beds)),
      el("td", { class: `num ${r.avg_physical_pct >= 100 ? "font-semibold" : ""}`,
                 style: r.avg_physical_pct >= filters.high_occupancy_pct ? "color: var(--status-critical)" : "" },
         `${fmt(r.avg_physical_pct)}%${r.avg_physical_pct >= filters.high_occupancy_pct ? " ▲" : ""}`),
      el("td", { class: "num" }, fmt(r.days_over_threshold)),
    ]))),
  ]));
}

function renderMatrix(m) {
  $("occ-matrix").replaceChildren(el("table", { class: "data-table w-full text-sm" }, [
    el("thead", {}, el("tr", {}, [el("th", { scope: "col" }, "Servicio"),
      ...m.months.map((mo) => el("th", { scope: "col", class: "num" }, fmtMonth(mo)))])),
    el("tbody", {}, m.rows.map((r) => el("tr", {}, [
      el("td", {}, r.service), ...r.values.map((v) => el("td", { class: "num" }, fmt(v)))]))),
  ]));
}

function selectService(service) {
  document.querySelector('input[name="mode"][value="service"]').checked = true;
  updateMode();
  $("occ-service").value = service;
  updateSubServices();
  load();
  $("occ-filters").scrollIntoView({ behavior: "smooth" });
}
