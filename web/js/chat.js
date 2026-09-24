// Chat con el agente NL2SQL: respuesta + gráfico + tabla + SQL desplegable + recomendaciones.
import { askAgent } from "./api.js";
import { chartFromAnswer } from "./charts.js";
import { dataTable, el } from "./ui.js";

const SUGGESTIONS = [
  "¿Cuántas camas de UCI están ocupadas hoy?",
  "¿Cuáles son los medicamentos con menos de 5 días de inventario?",
  "¿Cuál es el tiempo de espera promedio en urgencias en la última semana?",
  "¿Qué servicio tiene más pacientes ingresados este mes?",
  "¿Qué diferencia hay entre una EPS y una IPS?",
  "Explícame qué es el triage",
];
const SOURCE_LABELS = {
  rules: "Consulta verificada", llm: "Generada por IA", glossary: "Glosario HIS", assistant: "Asistente",
};
const TABLE_PREVIEW_ROWS = 10;

const $ = (id) => document.getElementById(id);

export function initChat() {
  $("suggestions").replaceChildren(...SUGGESTIONS.map((q) =>
    el("button", { class: "chip px-3 py-1.5 text-sm text-left", type: "button", onclick: () => ask(q) }, q)));
  $("chat-form").addEventListener("submit", (e) => {
    e.preventDefault();
    const q = $("question").value.trim();
    if (q.length >= 3) ask(q);
  });
}

async function ask(question) {
  const input = $("question");
  const button = $("ask");
  input.value = "";
  button.disabled = true;
  append(el("div", { class: "flex justify-end" }, el("p", { class: "bubble-user px-4 py-2 max-w-[85%] text-sm" }, question)));
  const pending = el("div", { class: "bubble-bot p-4 text-sm text-slate-500" }, "Consultando los datos del hospital…");
  append(pending);
  try {
    const answer = await askAgent(question);
    pending.replaceWith(renderAnswer(answer));
  } catch (e) {
    pending.replaceWith(el("div", { class: "bubble-bot p-4 text-sm accent-warning", role: "alert" }, e.message));
  } finally {
    button.disabled = false;
    input.focus();
  }
}

function append(node) {
  $("messages").append(node);
  node.scrollIntoView({ behavior: "smooth", block: "end" });
}

function renderAnswer(a) {
  const canvasBox = el("div", { class: "chart-box mt-3" });
  const box = el("div", { class: "bubble-bot p-4 space-y-3" }, [
    el("div", { class: "flex items-center gap-2 text-xs text-slate-500" }, [
      el("span", { class: "status status-ok" }, SOURCE_LABELS[a.source] || a.source),
      a.sql ? el("span", {}, `${a.rows.length} fila${a.rows.length === 1 ? "" : "s"}`) : null,
    ]),
    el("p", { class: "text-base whitespace-pre-line", style: "color: var(--text-primary)" }, a.answer),
  ]);

  if (a.chart && a.chart.type !== "none" && a.rows.length > 1) {
    const canvas = el("canvas", { role: "img", "aria-label": `Gráfico: ${a.answer}` });
    canvasBox.append(canvas);
    box.append(canvasBox);
    // Chart.js necesita el canvas en el DOM para medirlo
    requestAnimationFrame(() => { if (!chartFromAnswer(canvas, a)) canvasBox.remove(); });
  }

  if (a.rows.length) {
    const more = a.rows.length > TABLE_PREVIEW_ROWS;
    box.append(el("details", { open: !more || undefined }, [
      el("summary", { class: "text-sm font-medium", style: "color: var(--brand-green-dark)" },
         more ? `Ver los ${a.rows.length} registros` : "Datos"),
      el("div", { class: "overflow-auto max-h-80 mt-2" }, dataTable(a.columns, a.rows)),
    ]));
  }

  if (a.sql) {
    box.append(el("details", {}, [
      el("summary", { class: "text-sm font-medium text-slate-600" }, "Ver consulta SQL"),
      el("pre", { class: "sql mt-2" }, a.sql),
    ]));
  }

  if (a.recommendations?.length) {
    box.append(el("div", { class: "rounded-lg p-3", style: "background: var(--status-ok-bg)" }, [
      el("p", { class: "text-sm font-semibold mb-1", style: "color: var(--brand-green-dark)" }, "Recomendaciones"),
      el("ul", { class: "list-disc pl-5 text-sm space-y-1" }, a.recommendations.map((r) => el("li", {}, r))),
    ]));
  }
  if (a.sources?.length) {
    box.append(el("p", { class: "text-xs text-slate-400" }, `Fuente: ${a.sources.join(" · ")}`));
  }
  return box;
}
