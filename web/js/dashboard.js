// Panel principal: tarjetas KPI, gráficos, alertas, inventario y pestañas.
import { getAlerts, getKpis, getUser, logout } from "./api.js";
import { barChart, chartCard, doughnutChart, lineChart, SERIES } from "./charts.js";
import { initChat } from "./chat.js";
import { initImportPanel } from "./import.js";
import { initOccupancy } from "./occupancy.js";
import { el, fmt, fmtDate, statusBadge } from "./ui.js";

const $ = (id) => document.getElementById(id);
const state = { kpis: null, alerts: [], medsRendered: false, alertFilter: "" };

const ALERT_TYPES = {
  stock: "Desabastecimiento", occupancy: "Ocupación", wait_time: "Tiempos de espera",
  forecast: "Predictivas", expiry: "Vencimientos", surgery: "Cirugías",
};

// --- Arranque ----------------------------------------------------------------------

init();

async function init() {
  const user = getUser();
  $("user-name").textContent = user ? `${user.name} · ${user.username}` : "";
  $("logout").addEventListener("click", logout);
  setupTabs();
  initChat();
  initImportPanel();
  try {
    const [kpis, alerts] = await Promise.all([getKpis(), getAlerts()]);
    state.kpis = kpis;
    state.alerts = alerts;
    $("reference-date").textContent = fmtDate(kpis.reference_date);
    renderCards(kpis.cards);
    renderTopAlerts(alerts);
    renderSummaryCharts(kpis.series);
    renderAlertsTab();
    setupMedsTable(kpis.medications_table);
    if (kpis.admissions_table) setupAdmissionsTable(kpis.admissions_table);
  } catch (e) {
    $("load-error").textContent = `No se pudieron cargar los indicadores: ${e.message}`;
    $("load-error").classList.remove("hidden");
  } finally {
    $("loading").classList.add("hidden");
  }
}

function setupTabs() {
  const tabs = document.querySelectorAll('[role="tab"]');
  tabs.forEach((tab) => tab.addEventListener("click", () => showTab(tab.dataset.tab)));
}

export function showTab(name) {
  document.querySelectorAll('[role="tab"]').forEach((t) => t.setAttribute("aria-selected", String(t.dataset.tab === name)));
  document.querySelectorAll('[role="tabpanel"]').forEach((p) => p.classList.toggle("hidden", p.id !== `tab-${name}`));
  if (name === "meds" && state.kpis && !state.medsRendered) {
    renderMedsCharts(state.kpis.series);   // se dibujan al mostrarse para que Chart.js tome el tamaño real
    state.medsRendered = true;
  }
  if (name === "occupancy" && !state.occupancyStarted) {
    state.occupancyStarted = true;
    initOccupancy();   // se carga al abrir la pestaña
  }
  if (name === "assistant") $("question").focus();
}

// --- Tarjetas KPI ------------------------------------------------------------------

function renderCards(cards) {
  $("kpi-cards").replaceChildren(...cards.map((c) =>
    el("article", { class: `card p-4 accent-${c.status}` }, [
      el("div", { class: "flex items-start justify-between gap-2" }, [
        el("h3", { class: "text-sm text-slate-600" }, c.label),
        statusBadge(c.status),
      ]),
      el("p", { class: "font-display text-3xl font-semibold mt-2", style: "color: var(--brand-navy)" },
        [fmt(c.value), el("span", { class: "text-lg text-slate-500 ml-1" }, c.unit)]),
      el("p", { class: "text-xs text-slate-500 mt-1" }, c.detail),
    ])));
}

// --- Gráficos ----------------------------------------------------------------------

function renderSummaryCharts(s) {
  const box = $("summary-charts");

  lineChart(chartCard(box, { title: "Ocupación diaria sobre camas físicas", wide: true,
                             subtitle: "Últimos 30 días · sobre 100% = pacientes en camas virtuales" }), {
    labels: s.occupancy_daily.labels.map((d) => d.slice(5)),
    datasets: s.occupancy_daily.datasets, unit: "%",
    threshold: { value: s.occupancy_daily.threshold, label: `Alerta ${s.occupancy_daily.threshold}%` },
  });

  barChart(chartCard(box, { title: "Ocupación hoy por servicio", tall: true,
                            subtitle: "Pacientes / camas físicas (capacidad estimada)" }), {
    labels: s.occupancy_by_service.labels,
    datasets: [{ label: "Ocupación física", data: s.occupancy_by_service.data }],
    horizontal: true, unit: "%",
    threshold: { value: s.occupancy_by_service.threshold, label: `${s.occupancy_by_service.threshold}%` },
  });

  doughnutChart(chartCard(box, { title: "Distribución de ingresos por servicio", tall: true,
                                 subtitle: "Distribución (gráfico de pastel/dona) del mes en curso" }), {
    labels: s.admissions_by_service.labels,
    data: s.admissions_by_service.data,
    unit: " pacientes",
  });

  lineChart(chartCard(box, { title: "Ingresos diarios y tendencia", wide: true,
                             subtitle: "Últimos 60 días · la media móvil de 7 días alimenta las alertas predictivas" }), {
    labels: s.admissions_daily.labels.map((d) => d.slice(5)),
    datasets: [
      { label: "Ingresos del día", data: s.admissions_daily.data, color: SERIES[1] },
      { label: "Media móvil 7 días", data: s.admissions_daily.moving_avg_7d, color: SERIES[0] },
    ],
  });

  barChart(chartCard(box, { title: "Espera en urgencias por triage", subtitle: "Minutos de triage a primera atención" }), {
    labels: s.wait_by_triage.labels,
    datasets: [{ label: "Última semana", data: s.wait_by_triage.last_7d },
               { label: "Histórico", data: s.wait_by_triage.historical }],
    unit: " min",
  });

  barChart(chartCard(box, { title: "Cirugías programadas vs realizadas",
                            subtitle: "Por mes del ingreso · realizada = procedimiento facturado" }), {
    labels: s.surgery.labels,
    datasets: [{ label: "Programadas", data: s.surgery.scheduled }, { label: "Realizadas", data: s.surgery.performed }],
  });

  barChart(chartCard(box, { title: "Especialidades más solicitadas", wide: true,
                            subtitle: "Ingresos distintos atendidos por especialidad" }), {
    labels: s.top_specialties.labels, datasets: [{ label: "Ingresos atendidos", data: s.top_specialties.data }],
    horizontal: true,
  });
}

function renderMedsCharts(s) {
  const box = $("meds-charts");
  barChart(chartCard(box, { title: "Mayor rotación (30 días)", tall: true, subtitle: "Unidades dispensadas" }), {
    labels: s.top_medications.labels, datasets: [{ label: "Unidades", data: s.top_medications.data }], horizontal: true,
  });
  barChart(chartCard(box, { title: "Menor rotación (30 días)", tall: true, subtitle: "Candidatos a revisar compra o redistribuir" }), {
    labels: s.low_medications.labels, datasets: [{ label: "Unidades", data: s.low_medications.data, color: SERIES[3] }],
    horizontal: true,
  });
}

// --- Alertas -----------------------------------------------------------------------

function alertCard(a, compact = false) {
  return el("article", { class: `card p-4 accent-${a.severity}` }, [
    el("div", { class: "flex flex-wrap items-center gap-2" }, [
      statusBadge(a.severity),
      el("span", { class: "text-xs text-slate-500" }, ALERT_TYPES[a.type] || a.type),
    ]),
    el("h3", { class: "font-semibold mt-1", style: "color: var(--brand-navy)" }, a.title),
    compact ? null : el("p", { class: "text-sm text-slate-600 mt-1" }, a.detail),
    el("p", { class: "text-sm mt-2" }, [el("strong", {}, "Recomendación: "), a.action]),
  ]);
}

function renderTopAlerts(alerts) {
  const critical = alerts.filter((a) => a.severity === "critical");
  $("alerts-count").textContent = critical.length || "";
  if (!critical.length) return;
  // La más importante de cada tipo (no tres de medicamentos seguidas)
  const seen = new Set();
  const firstOfEachType = critical.filter((a) => !seen.has(a.type) && seen.add(a.type));
  const highlights = [...firstOfEachType, ...critical.filter((a) => !firstOfEachType.includes(a))].slice(0, 3);
  $("top-alerts").replaceChildren(
    el("div", { class: "flex items-center justify-between" }, [
      el("h2", { class: "font-display font-semibold", style: "color: var(--brand-navy)" }, "Requiere acción hoy"),
      el("button", { class: "text-sm underline", style: "color: var(--brand-green-dark)", onclick: () => showTab("alerts") },
         `Ver las ${alerts.length} alertas`),
    ]),
    el("div", { class: "grid grid-cols-1 md:grid-cols-3 gap-3" }, highlights.map((a) => alertCard(a, true))),
  );
}

function renderAlertsTab() {
  const types = ["", ...new Set(state.alerts.map((a) => a.type))];
  $("alert-filters").replaceChildren(...types.map((t) => {
    const count = t ? state.alerts.filter((a) => a.type === t).length : state.alerts.length;
    return el("button", {
      class: "chip px-3 py-1 text-sm", "aria-pressed": String(state.alertFilter === t),
      style: state.alertFilter === t ? "border-color: var(--brand-green-dark); color: var(--brand-green-dark); font-weight: 600" : "",
      onclick: () => { state.alertFilter = t; renderAlertsTab(); },
    }, `${t ? ALERT_TYPES[t] || t : "Todas"} (${count})`);
  }));
  const list = state.alerts.filter((a) => !state.alertFilter || a.type === state.alertFilter);
  $("alert-list").replaceChildren(...list.map((a) => alertCard(a)));
}

// --- Inventario --------------------------------------------------------------------

function setupMedsTable(rows) {
  const search = $("meds-search");
  const status = $("meds-status");
  const render = () => {
    const q = search.value.trim().toLowerCase();
    const filtered = rows.filter((r) => (!status.value || r.status === status.value)
      && (!q || r.item_name.toLowerCase().includes(q) || r.item_code.toLowerCase().includes(q)));
    $("meds-count").textContent = `${fmt(filtered.length)} de ${fmt(rows.length)} medicamentos`;
    $("meds-table").replaceChildren(el("table", { class: "data-table w-full text-sm" }, [
      el("thead", {}, el("tr", {}, [
        el("th", { scope: "col" }, "Medicamento"), el("th", { scope: "col" }, "Código"),
        el("th", { scope: "col", class: "num" }, "Stock (und)"), el("th", { scope: "col", class: "num" }, "Consumo diario"),
        el("th", { scope: "col", class: "num" }, "Días de inventario"), el("th", { scope: "col" }, "Vence"),
        el("th", { scope: "col" }, "Estado"),
      ])),
      el("tbody", {}, filtered.map((r) => el("tr", {}, [
        el("td", {}, r.item_name), el("td", { class: "text-slate-500" }, r.item_code),
        el("td", { class: "num" }, fmt(r.stock_units)), el("td", { class: "num" }, fmt(r.avg_daily_consumption)),
        el("td", { class: "num font-semibold" }, fmt(r.days_of_inventory)), el("td", { class: "tabular" }, r.expiry_date),
        el("td", {}, statusBadge(r.status)),
      ]))),
    ]));
  };
  search.addEventListener("input", render);
  status.addEventListener("change", render);
  render();
}

// --- Listado dinámico de pacientes / admisiones (sin datos sensibles) --------------

const CHAPTER_DESCRIPTIONS = {
  A: "Infecciosas", B: "Infecciosas", C: "Oncológicas", D: "Hematológicas",
  E: "Endocrinas", F: "Salud mental", G: "Neurológicas", H: "Ojo y oído",
  I: "Cardiovasculares", J: "Respiratorias", K: "Digestivas", L: "Piel",
  M: "Osteomusculares", N: "Genitourinarias", O: "Obstétricas", P: "Perinatales",
  Q: "Malformaciones", R: "Síntomas generales", S: "Traumatismos", T: "Intoxicaciones / Traumas",
  Z: "Controles y otros",
};

function setupAdmissionsTable(rows) {
  const search = $("adm-search");
  if (!search || !rows) return;
  const render = () => {
    const q = search.value.trim().toLowerCase();
    const filtered = rows.filter((r) => {
      if (!q) return true;
      const chDesc = (CHAPTER_DESCRIPTIONS[r.diagnosis_chapter] || "").toLowerCase();
      return (r.service && r.service.toLowerCase().includes(q))
        || (r.sub_service && r.sub_service.toLowerCase().includes(q))
        || (r.diagnosis_chapter && r.diagnosis_chapter.toLowerCase().includes(q))
        || (r.sex && r.sex.toLowerCase().includes(q))
        || chDesc.includes(q);
    });
    $("adm-count").textContent = `Mostrando ${fmt(filtered.length)} de ${fmt(rows.length)} ingresos recientes`;
    $("adm-table").replaceChildren(el("table", { class: "data-table w-full text-sm" }, [
      el("thead", {}, el("tr", {}, [
        el("th", { scope: "col" }, "Fecha ingreso"),
        el("th", { scope: "col" }, "Servicio"),
        el("th", { scope: "col" }, "Subservicio"),
        el("th", { scope: "col" }, "Vía"),
        el("th", { scope: "col" }, "Sexo"),
        el("th", { scope: "col" }, "Edad"),
        el("th", { scope: "col" }, "Capítulo CIE-10"),
        el("th", { scope: "col", class: "num" }, "Estancia (días)"),
      ])),
      el("tbody", {}, filtered.map((r) => el("tr", {}, [
        el("td", { class: "tabular text-xs" }, r.admission_at),
        el("td", { class: "font-medium" }, r.service),
        el("td", { class: "text-slate-500 text-xs" }, r.sub_service || "—"),
        el("td", {}, r.admission_route || "—"),
        el("td", {}, r.sex || "—"),
        el("td", {}, r.age_group || "—"),
        el("td", {}, [
          el("span", { class: "font-mono font-semibold mr-1" }, r.diagnosis_chapter || "—"),
          el("span", { class: "text-xs text-slate-500" }, CHAPTER_DESCRIPTIONS[r.diagnosis_chapter] ? `(${CHAPTER_DESCRIPTIONS[r.diagnosis_chapter]})` : ""),
        ]),
        el("td", { class: "num font-semibold" }, r.length_of_stay_days != null ? fmt(r.length_of_stay_days) : "—"),
      ]))),
    ]));
  };
  search.addEventListener("input", render);
  render();
}

