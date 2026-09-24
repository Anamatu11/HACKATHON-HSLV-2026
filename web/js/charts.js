// Fábrica de gráficos Chart.js con la paleta validada y las reglas de la guía de visualización:
// marcas finas, cuadrícula discreta, un solo eje Y, leyenda solo con >= 2 series, tooltips siempre.
/* global Chart */
import { columnLabel, dataTable, el, fmt } from "./ui.js";

const css = getComputedStyle(document.documentElement);
const token = (name) => css.getPropertyValue(name).trim();
export const SERIES = ["--series-1", "--series-2", "--series-3", "--series-4"].map(token);
const TEXT_MUTED = token("--text-muted");
const TEXT_SECONDARY = token("--text-secondary");
const GRID = token("--grid");

Chart.defaults.font.family = 'system-ui, -apple-system, "Segoe UI", Roboto, sans-serif';
Chart.defaults.font.size = 12;
Chart.defaults.color = TEXT_SECONDARY;
Chart.defaults.maintainAspectRatio = false;
Chart.defaults.plugins.tooltip.callbacks.label = (ctx) =>
  `${ctx.dataset.label ? `${ctx.dataset.label}: ` : ""}${fmt(ctx.parsed[ctx.chart.options.indexAxis === "y" ? "x" : "y"])}`;

// Línea de referencia (meta/umbral) sobre el eje de valores, con su etiqueta.
const thresholdPlugin = {
  id: "threshold",
  afterDatasetsDraw(chart, _args, opts) {
    if (opts?.value === undefined || opts.value === null) return;
    const horizontal = chart.options.indexAxis === "y";
    const scale = chart.scales[horizontal ? "x" : "y"];
    const pos = scale.getPixelForValue(opts.value);
    const { top, bottom, left, right } = chart.chartArea;
    const c = chart.ctx;
    const color = opts.color || token("--status-critical");
    c.save();
    c.strokeStyle = color;
    c.lineWidth = 1.5;
    c.setLineDash(opts.solid ? [] : [5, 4]);
    c.beginPath();
    if (horizontal) { c.moveTo(pos, top); c.lineTo(pos, bottom); } else { c.moveTo(left, pos); c.lineTo(right, pos); }
    c.stroke();
    c.setLineDash([]);
    c.fillStyle = color;
    c.font = "600 11px system-ui, sans-serif";
    if (horizontal) { c.textAlign = "left"; c.fillText(opts.label, pos + 4, top + 10); }
    else { c.textAlign = "right"; c.fillText(opts.label, right, pos - 4); }
    c.restore();
  },
};
// Tramo sombreado (p. ej. datos incompletos) desde un índice de categoría hasta el final del eje X.
const shadePlugin = {
  id: "shade",
  beforeDatasetsDraw(chart, _args, opts) {
    if (opts?.fromIndex === undefined || opts.fromIndex === null || opts.fromIndex < 0) return;
    const x = chart.scales.x;
    const { top, bottom, right } = chart.chartArea;
    const halfStep = (x.width / Math.max(1, chart.data.labels.length)) / 2;
    const start = x.getPixelForValue(opts.fromIndex) - halfStep;
    // toIndex queda FUERA del sombreado (p. ej. "hoy", que sí es confiable)
    const end = opts.toIndex !== undefined ? x.getPixelForValue(opts.toIndex) - halfStep : right;
    const c = chart.ctx;
    c.save();
    c.fillStyle = "rgba(123, 122, 140, 0.12)";
    c.fillRect(start, top, end - start, bottom - top);
    c.fillStyle = TEXT_MUTED;
    c.font = "600 11px system-ui, sans-serif";
    c.textAlign = "left";
    c.fillText(opts.label || "", start + 4, top + 12);
    c.restore();
  },
};
Chart.register(thresholdPlugin, shadePlugin);

const registry = new Map();

function mount(canvas, config) {
  registry.get(canvas)?.destroy();
  const chart = new Chart(canvas, config);
  registry.set(canvas, chart);
  return chart;
}

function axes({ horizontal = false, unit = "", max } = {}) {
  const valueAxis = {
    beginAtZero: true, max,
    grid: { color: GRID, drawTicks: false }, border: { display: false },
    ticks: { color: TEXT_MUTED, padding: 6, callback: (v) => `${fmt(v)}${unit}` },
  };
  const categoryAxis = {
    grid: { display: false }, border: { color: GRID },
    ticks: { color: TEXT_MUTED, autoSkip: true, maxRotation: 0,
             callback(value) { const l = this.getLabelForValue(value); return String(l).length > 28 ? `${String(l).slice(0, 26)}…` : l; } },
  };
  return horizontal ? { x: valueAxis, y: categoryAxis } : { x: categoryAxis, y: valueAxis };
}

function legend(datasets) {
  return { display: datasets.length >= 2, position: "top", align: "start",
           labels: { usePointStyle: true, pointStyle: "rectRounded", boxWidth: 10, boxHeight: 10, color: TEXT_SECONDARY } };
}

/** Líneas (series temporales). datasets: [{label, data}] -> colores por orden fijo. */
export function lineChart(canvas, { labels, datasets, unit = "", threshold, max, shade }) {
  const ds = datasets.map((d, i) => ({
    label: d.label, data: d.data, borderColor: d.color || SERIES[i], backgroundColor: d.color || SERIES[i],
    borderWidth: 2, pointRadius: 0, pointHoverRadius: 5, tension: 0.25, spanGaps: true,
    borderDash: d.dashed ? [6, 4] : undefined,
  }));
  return mount(canvas, {
    type: "line",
    data: { labels, datasets: ds },
    options: {
      interaction: { mode: "index", intersect: false },
      scales: axes({ unit, max }),
      plugins: { legend: legend(ds), threshold: threshold ? { value: threshold.value, label: threshold.label } : {},
                 shade: shade || {} },
    },
  });
}

/** Barras. Una serie = un solo color; varias series = orden fijo de la paleta.
 *  d.color puede ser un arreglo (un color por barra, p. ej. estado). tooltipAfter(i) agrega líneas al tooltip. */
export function barChart(canvas, { labels, datasets, horizontal = false, unit = "", threshold, tooltipAfter,
                                   maxBarThickness = 26 }) {
  const ds = datasets.map((d, i) => ({
    label: d.label, data: d.data, backgroundColor: d.color || SERIES[i],
    borderRadius: 4, borderSkipped: "start", maxBarThickness,
    categoryPercentage: 0.8, barPercentage: 0.9,
  }));
  return mount(canvas, {
    type: "bar",
    data: { labels, datasets: ds },
    options: {
      indexAxis: horizontal ? "y" : "x",
      interaction: { mode: "index", intersect: false },
      scales: axes({ horizontal, unit }),
      plugins: {
        legend: legend(ds),
        threshold: threshold || {},
        tooltip: tooltipAfter ? { callbacks: { afterBody: (items) => tooltipAfter(items[0].dataIndex) } } : {},
      },
    },
  });
}

/** Gráfico para una respuesta del agente: {chart: {type, x, y}, columns, rows}. Devuelve null si no aplica. */
export function chartFromAnswer(canvas, { chart, columns, rows }) {
  if (!chart || chart.type === "none" || !rows.length) return null;
  const xi = columns.indexOf(chart.x);
  const yi = columns.indexOf(chart.y);
  if (xi < 0 || yi < 0) return null;
  const labels = rows.map((r) => (typeof r[xi] === "number" ? `${columnLabel(chart.x)} ${r[xi]}` : r[xi]));
  const data = rows.map((r) => r[yi]);
  const label = columnLabel(chart.y);
  if (chart.type === "line") return lineChart(canvas, { labels, datasets: [{ label, data }] });
  const horizontal = labels.some((l) => String(l).length > 12) || labels.length > 8;
  return barChart(canvas, { labels, datasets: [{ label, data }], horizontal });
}

export const chartOf = (canvas) => registry.get(canvas);

/** Tarjeta de gráfico con botón "Ver tabla" (alternativa accesible a los colores). Devuelve el canvas. */
export function chartCard(container, { title, subtitle, tall = false, wide = false }) {
  const canvas = el("canvas", { role: "img", "aria-label": title });
  const tableBox = el("div", { class: "hidden overflow-auto max-h-72 mt-2" });
  const toggle = el("button", {
    class: "text-xs text-slate-600 border border-slate-200 rounded-md px-2 py-1 hover:bg-slate-50", type: "button",
    onclick: () => {
      const showing = !tableBox.classList.contains("hidden");
      tableBox.classList.toggle("hidden", showing);
      toggle.textContent = showing ? "Ver tabla" : "Ocultar tabla";
      if (!showing) tableBox.replaceChildren(tableFromChart(chartOf(canvas)));
    },
  }, "Ver tabla");
  container.append(el("article", { class: `card p-4 ${wide ? "lg:col-span-2" : ""}` }, [
    el("div", { class: "flex items-start justify-between gap-2 mb-2" }, [
      el("div", {}, [el("h3", { class: "font-display font-semibold text-sm", style: "color: var(--brand-navy)" }, title),
                     subtitle ? el("p", { class: "text-xs text-slate-500" }, subtitle) : null]),
      toggle,
    ]),
    el("div", { class: `chart-box ${tall ? "tall" : ""}` }, canvas),
    tableBox,
  ]));
  return canvas;
}

function tableFromChart(chart) {
  if (!chart) return el("p", {}, "Sin datos");
  const { labels, datasets } = chart.data;
  return dataTable(["", ...datasets.map((d) => d.label || "Valor")],
                   labels.map((l, i) => [l, ...datasets.map((d) => d.data[i])]));
}
