// Fábrica de gráficos Chart.js con la paleta validada y las reglas de la guía de visualización:
// marcas finas, cuadrícula discreta, un solo eje Y, leyenda solo con >= 2 series, tooltips siempre.
/* global Chart */
import { columnLabel, fmt } from "./ui.js";

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
    c.save();
    c.strokeStyle = token("--status-critical");
    c.lineWidth = 1.5;
    c.setLineDash([5, 4]);
    c.beginPath();
    if (horizontal) { c.moveTo(pos, top); c.lineTo(pos, bottom); } else { c.moveTo(left, pos); c.lineTo(right, pos); }
    c.stroke();
    c.setLineDash([]);
    c.fillStyle = token("--status-critical");
    c.font = "600 11px system-ui, sans-serif";
    if (horizontal) { c.textAlign = "left"; c.fillText(opts.label, pos + 4, top + 10); }
    else { c.textAlign = "right"; c.fillText(opts.label, right, pos - 4); }
    c.restore();
  },
};
Chart.register(thresholdPlugin);

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
export function lineChart(canvas, { labels, datasets, unit = "", threshold, max }) {
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
      plugins: { legend: legend(ds), threshold: threshold ? { value: threshold.value, label: threshold.label } : {} },
    },
  });
}

/** Barras. Una serie = un solo color; varias series = orden fijo de la paleta. */
export function barChart(canvas, { labels, datasets, horizontal = false, unit = "", threshold }) {
  const ds = datasets.map((d, i) => ({
    label: d.label, data: d.data, backgroundColor: d.color || SERIES[i],
    borderRadius: 4, borderSkipped: "start", maxBarThickness: 26,
    categoryPercentage: 0.8, barPercentage: 0.9,
  }));
  return mount(canvas, {
    type: "bar",
    data: { labels, datasets: ds },
    options: {
      indexAxis: horizontal ? "y" : "x",
      interaction: { mode: "index", intersect: false },
      scales: axes({ horizontal, unit }),
      plugins: { legend: legend(ds), threshold: threshold ? { value: threshold.value, label: threshold.label } : {} },
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
