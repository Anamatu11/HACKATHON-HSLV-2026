// Cliente de la API: agrega el token JWT y redirige al login si la sesión no es válida.

const TOKEN_KEY = "hslv_token";
const USER_KEY = "hslv_user";

export function saveSession({ access_token, user }, remember) {
  const store = remember ? localStorage : sessionStorage;
  store.setItem(TOKEN_KEY, access_token);
  store.setItem(USER_KEY, JSON.stringify(user));
}

export function getToken() {
  return sessionStorage.getItem(TOKEN_KEY) || localStorage.getItem(TOKEN_KEY);
}

export function getUser() {
  const raw = sessionStorage.getItem(USER_KEY) || localStorage.getItem(USER_KEY);
  try { return raw ? JSON.parse(raw) : null; } catch { return null; }
}

export function logout() {
  [sessionStorage, localStorage].forEach((s) => { s.removeItem(TOKEN_KEY); s.removeItem(USER_KEY); });
  window.location.href = "index.html";
}

/** fetch a /api/* con token. Lanza Error con el mensaje del backend ({error} o {detail}). */
export async function api(path, { method = "GET", body } = {}) {
  const headers = { "Content-Type": "application/json" };
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;

  const res = await fetch(path, { method, headers, body: body ? JSON.stringify(body) : undefined });
  if (res.status === 401 && !path.startsWith("/api/auth/login")) {
    logout();
    throw new Error("Sesión expirada");
  }
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail = Array.isArray(data.detail) ? "Revise los datos enviados." : data.detail;
    throw new Error(data.error || detail || `Error ${res.status}`);
  }
  return data;
}

export const login = (username, password) =>
  api("/api/auth/login", { method: "POST", body: { username, password } });
export const getKpis = () => api("/api/kpis");
export const getAlerts = () => api("/api/alerts");
export const askAgent = (question) => api("/api/query", { method: "POST", body: { question } });
export const getMe = () => api("/api/auth/me");
export const getOccupancyFilters = () => api("/api/occupancy/filters");
export const getOccupancy = (params) => {
  const query = new URLSearchParams(Object.entries(params).filter(([, v]) => v !== "" && v != null));
  return api(`/api/occupancy?${query}`);
};
/** Descarga el informe PDF de una consulta (solo Gerencia / Dirección). Devuelve el nombre del archivo. */
export async function downloadReport(queryId) {
  const res = await fetch(`/api/reports/${encodeURIComponent(queryId)}`, {
    method: "POST", headers: { Authorization: `Bearer ${getToken()}` },
  });
  if (res.status === 401) { logout(); throw new Error("Sesión expirada"); }
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error(data.error || data.detail || `Error ${res.status}`);
  }
  const name = /filename="([^"]+)"/.exec(res.headers.get("Content-Disposition") || "")?.[1] || "informe_HSLV.pdf";
  const url = URL.createObjectURL(await res.blob());
  const link = Object.assign(document.createElement("a"), { href: url, download: name });
  document.body.append(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 10_000);
  return name;
}

export const getPermissions = () => api("/api/permissions");
export const savePermissions = (matrix) => api("/api/permissions", { method: "PUT", body: { matrix } });
export const getUsers = () => api("/api/users");
export const createUser = (user) => api("/api/users", { method: "POST", body: user });
export const updateUser = (username, changes) =>
  api(`/api/users/${encodeURIComponent(username)}`, { method: "PATCH", body: changes });
export const deleteUser = (username) => api(`/api/users/${encodeURIComponent(username)}`, { method: "DELETE" });
