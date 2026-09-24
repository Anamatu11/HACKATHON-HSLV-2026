// Pestaña Permisos: matriz rol × módulo y administración de usuarios (solo Gerencia / Dirección).
import { createUser, deleteUser, getPermissions, getUser, getUsers, savePermissions, updateUser } from "./api.js";
import { el } from "./ui.js";

const $ = (id) => document.getElementById(id);
const state = { config: null, matrix: null, users: [] };

export async function initPermissions() {
  $("perm-save").addEventListener("click", onSaveMatrix);
  $("user-form").addEventListener("submit", onCreateUser);
  $("user-role").addEventListener("change", toggleServiceField);
  try {
    const [config, users] = await Promise.all([getPermissions(), getUsers()]);
    state.config = config;
    state.matrix = structuredClone(config.matrix);
    state.users = users;
    fillFormOptions();
    renderMatrix();
    renderUsers();
  } catch (e) {
    showMessage("perm-error", `No se pudieron cargar los permisos: ${e.message}`);
  }
}

// --- Mensajes ------------------------------------------------------------------------

function showMessage(id, text) {
  ["perm-error", "perm-ok"].forEach((x) => $(x).classList.add("hidden"));
  $(id).textContent = text;
  $(id).classList.remove("hidden");
}

const roleLabel = (key) => state.config.roles.find((r) => r.key === key)?.label || key;
const isLocked = (role, module) => state.config.locked.some(([r, m]) => r === role && m === module);

// --- Matriz --------------------------------------------------------------------------

function renderMatrix() {
  const { roles, modules } = state.config;
  $("perm-matrix").replaceChildren(el("table", { class: "data-table w-full text-sm" }, [
    el("thead", {}, el("tr", {}, [
      el("th", { scope: "col" }, "Módulo"),
      ...roles.map((r) => el("th", { scope: "col", class: "text-center" }, r.label)),
    ])),
    el("tbody", {}, modules.map((m) => el("tr", {}, [
      el("th", { scope: "row", class: "font-normal" }, [
        el("span", { class: "font-medium", style: "color: var(--brand-navy)" }, m.label),
        el("span", { class: "block text-xs text-slate-500" }, m.detail),
      ]),
      ...roles.map((r) => el("td", { class: "text-center" }, el("input", {
        type: "checkbox", class: "w-4 h-4", style: "accent-color: var(--brand-green-dark)",
        "aria-label": `${m.label} para ${r.label}`,
        checked: state.matrix[r.key][m.key], disabled: isLocked(r.key, m.key),
        title: isLocked(r.key, m.key) ? "Dirección conserva siempre este módulo" : null,
        onchange: (ev) => { state.matrix[r.key][m.key] = ev.target.checked; },
      }))),
    ]))),
  ]));
}

async function onSaveMatrix() {
  const button = $("perm-save");
  button.disabled = true;
  try {
    const config = await savePermissions(state.matrix);
    state.config = config;
    state.matrix = structuredClone(config.matrix);
    renderMatrix();
    showMessage("perm-ok", "Permisos guardados. Los usuarios verán los cambios al recargar el panel.");
  } catch (e) {
    showMessage("perm-error", e.message);
  } finally {
    button.disabled = false;
  }
}

// --- Usuarios ------------------------------------------------------------------------

function fillFormOptions() {
  $("user-role").replaceChildren(...state.config.roles.map((r) =>
    el("option", { value: r.key, selected: r.key === "service_head" }, r.label)));
  $("user-service").replaceChildren(
    el("option", { value: "" }, "Seleccione…"),
    ...state.config.services.map((s) => el("option", { value: s }, s)));
  toggleServiceField();
}

function toggleServiceField() {
  const isHead = $("user-role").value === "service_head";
  $("user-service-box").classList.toggle("invisible", !isHead);
  $("user-service").required = isHead;
}

async function onCreateUser(ev) {
  ev.preventDefault();
  const form = ev.target;
  const data = Object.fromEntries(new FormData(form));
  if (data.role !== "service_head") delete data.service;
  try {
    await createUser(data);
    form.reset();
    fillFormOptions();
    await reloadUsers();
    showMessage("perm-ok", `Usuario ${data.username.toLowerCase()} creado como ${roleLabel(data.role)}.`);
  } catch (e) {
    showMessage("perm-error", e.message);
  }
}

async function reloadUsers() {
  state.users = await getUsers();
  renderUsers();
}

async function run(action, okText) {
  try {
    await action();
    await reloadUsers();
    showMessage("perm-ok", okText);
  } catch (e) {
    showMessage("perm-error", e.message);
  }
}

function renderUsers() {
  const me = getUser()?.username;
  $("user-table").replaceChildren(el("table", { class: "data-table w-full text-sm" }, [
    el("thead", {}, el("tr", {}, ["Usuario", "Nombre", "Rol", "Servicio", "Estado", "Acciones"]
      .map((h) => el("th", { scope: "col" }, h)))),
    el("tbody", {}, state.users.map((u) => el("tr", {}, [
      el("td", { class: "font-medium" }, u.username),
      el("td", {}, u.name),
      el("td", {}, u.built_in ? roleLabel(u.role) : roleSelect(u)),
      el("td", { class: "text-slate-600" }, !u.built_in && u.role === "service_head" ? serviceSelect(u) : u.service || "—"),
      el("td", {}, el("span", { class: `status ${u.active ? "status-ok" : "status-warning"}` }, u.active ? "Activo" : "Inactivo")),
      el("td", {}, u.built_in
        ? el("span", { class: "text-xs text-slate-500" }, "Usuario del .env (no editable)")
        : el("div", { class: "flex flex-wrap gap-2" }, [
          el("button", {
            class: "chip px-3 py-1 text-xs", disabled: u.username === me,
            onclick: () => run(() => updateUser(u.username, { active: !u.active }),
                               `Usuario ${u.username} ${u.active ? "desactivado" : "activado"}.`),
          }, u.active ? "Desactivar" : "Activar"),
          deleteButton(u, me),
        ])),
    ]))),
  ]));
}

function roleSelect(u) {
  return el("select", {
    class: "border border-slate-300 rounded-lg px-2 py-1 text-xs bg-white", "aria-label": `Rol de ${u.username}`,
    onchange: (ev) => {
      const role = ev.target.value;
      let service = u.service;
      // Un jefe de servicio necesita servicio: se asigna el primero y se ajusta en la columna Servicio
      if (role === "service_head" && !service) service = state.config.services[0];
      run(() => updateUser(u.username, { role, service }),
          `Rol de ${u.username}: ${roleLabel(role)}.${role === "service_head" ? " Verifique su servicio." : ""}`);
    },
  }, state.config.roles.map((r) => el("option", { value: r.key, selected: r.key === u.role }, r.label)));
}

function serviceSelect(u) {
  const options = state.config.services.includes(u.service) ? state.config.services : [u.service, ...state.config.services];
  return el("select", {
    class: "border border-slate-300 rounded-lg px-2 py-1 text-xs bg-white", "aria-label": `Servicio de ${u.username}`,
    onchange: (ev) => run(() => updateUser(u.username, { service: ev.target.value }),
                          `Servicio de ${u.username}: ${ev.target.value}.`),
  }, options.map((s) => el("option", { value: s, selected: s === u.service }, s)));
}

// Confirmación en dos pasos dentro de la página (sin confirm(), que no siempre está disponible)
function deleteButton(u, me) {
  const button = el("button", {
    class: "chip px-3 py-1 text-xs", style: "color: var(--status-critical)", disabled: u.username === me,
  }, "Eliminar");
  button.addEventListener("click", () => {
    if (button.dataset.armed) {
      run(() => deleteUser(u.username), `Usuario ${u.username} eliminado.`);
      return;
    }
    button.dataset.armed = "1";
    button.textContent = "¿Confirmar?";
    setTimeout(() => { delete button.dataset.armed; button.textContent = "Eliminar"; }, 4000);
  });
  return button;
}
