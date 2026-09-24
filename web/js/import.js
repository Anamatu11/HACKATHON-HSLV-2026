/**
 * Módulo de importación y validación de archivos crudos del HIS.
 * Valida columnas antes de procesar para evitar subir archivos en casillas equivocadas
 * y previene la duplicación de archivos entre casillas.
 */
import { EXPECTED_COLUMNS, FILE_METADATA } from "./import-schema.js";
import { el } from "./ui.js";

const DELIMITERS = ["|", ";", "\t", ","];

// Registro en memoria de archivos asignados por casilla: { [key]: { name, size, columns, file } }
const assignedFiles = {};

export function initImportPanel() {
  const container = document.getElementById("import-panel-container");
  if (!container) return;

  container.innerHTML = "";
  container.appendChild(renderImportCard());
}

function renderImportCard() {
  const card = el("article", { class: "card p-5 space-y-4 border border-slate-200" });

  // Encabezado del paso según la imagen de referencia
  const header = el("div", { class: "border-b border-slate-100 pb-3" }, [
    el("h3", { class: "font-display font-semibold text-base text-slate-800" }, "Importar datos"),
    el("p", { class: "text-xs text-slate-500 mt-1" },
      "Selecciona la categoría de datos y el archivo correspondiente para validar sus columnas antes de importarlo."
    )
  ]);

  // Campo "Tipo de archivo" con el desplegable
  const typeField = el("div", { class: "space-y-1.5" }, [
    el("label", { for: "import-file-type", class: "block text-xs font-semibold text-slate-600" }, "Tipo de archivo"),
    el("select", {
      id: "import-file-type",
      class: "w-full sm:max-w-md h-10 px-3 border border-slate-300 rounded-lg text-sm bg-white focus:outline-none focus:ring-2 focus:ring-emerald-600 focus:border-transparent cursor-pointer shadow-sm transition"
    }, [
      el("option", { value: "", disabled: "true", selected: "true" }, "— Seleccione el tipo de archivo crudo —"),
      ...Object.entries(FILE_METADATA).map(([key, meta]) =>
        el("option", { value: key, id: `opt-${key}` }, meta.label)
      )
    ])
  ]);

  // Área de selección de archivo
  const fileArea = el("div", { id: "import-file-area", class: "space-y-2 pt-2 border-t border-slate-100" }, [
    el("label", { for: "import-file-input", class: "block text-xs font-semibold text-slate-600" }, "Seleccionar archivo crudo (.txt)"),
    el("div", { class: "flex flex-wrap items-center gap-3" }, [
      el("input", {
        type: "file",
        id: "import-file-input",
        accept: ".txt,.csv",
        class: "text-xs file:mr-3 file:py-2 file:px-4 file:rounded-lg file:border-0 file:text-xs file:font-semibold file:bg-slate-100 file:text-slate-700 hover:file:bg-slate-200 cursor-pointer"
      }),
      el("span", { id: "file-meta-hint", class: "text-xs text-slate-400 italic" }, "Ningún archivo seleccionado")
    ])
  ]);

  // Contenedor para el resultado de validación
  const validationResult = el("div", { id: "import-validation-box", class: "hidden mt-3 p-3.5 rounded-lg text-xs transition space-y-2" });

  // Botón de guardar / cargar
  const actions = el("div", { class: "pt-2 flex flex-wrap items-center justify-between gap-3" }, [
    el("button", {
      id: "btn-import-save",
      disabled: "true",
      type: "button",
      class: "btn-primary px-4 py-2 rounded-lg text-xs font-semibold shadow-sm transition disabled:opacity-50 disabled:cursor-not-allowed"
    }, "Confirmar archivo para esta casilla"),
    el("span", { id: "import-btn-reason", class: "text-xs text-slate-400" }, "Selecciona un tipo y archivo válido")
  ]);

  card.append(header, typeField, fileArea, validationResult, actions);

  // Event Listeners y configuración inicial
  setTimeout(() => {
    const select = document.getElementById("import-file-type");
    const fileInput = document.getElementById("import-file-input");
    const saveBtn = document.getElementById("btn-import-save");

    const revalidate = () => {
      const typeKey = select.value;
      const file = fileInput.files[0];
      if (!typeKey || !file) {
        hideValidation();
        return;
      }
      validateSelectedFile(file, typeKey);
    };

    select?.addEventListener("change", revalidate);
    fileInput?.addEventListener("change", revalidate);

    saveBtn?.addEventListener("click", () => {
      const typeKey = select.value;
      const file = fileInput.files[0];
      if (!typeKey || !file) return;

      // Guardar en el registro de asignaciones
      assignedFiles[typeKey] = {
        name: file.name,
        size: file.size,
        file: file,
        assignedAt: new Date().toLocaleTimeString()
      };

      revalidate(); // refresca mensaje a estado "Guardado"
    });
  }, 0);

  return card;
}

function hideValidation() {
  const box = document.getElementById("import-validation-box");
  const btn = document.getElementById("btn-import-save");
  const reason = document.getElementById("import-btn-reason");
  if (box) box.classList.add("hidden");
  if (btn) btn.disabled = true;
  if (reason) reason.textContent = "Selecciona un tipo y archivo válido";
}

/**
 * Lee la primera línea (cabecera) del archivo y compara columnas contra el esquema esperado,
 * además de validar que no sea un archivo duplicado ya asignado a otra casilla.
 */
async function validateSelectedFile(file, typeKey) {
  const box = document.getElementById("import-validation-box");
  const btn = document.getElementById("btn-import-save");
  const reason = document.getElementById("import-btn-reason");
  const metaHint = document.getElementById("file-meta-hint");
  if (!box) return;

  metaHint.textContent = `${file.name} (${(file.size / 1024).toFixed(1)} KB)`;
  box.classList.remove("hidden");
  box.innerHTML = "<p class='text-slate-500'>Analizando archivo y estructura de columnas...</p>";

  // 1. VALIDACIÓN DE DUPLICADOS CRUZADOS:
  // ¿Este mismo archivo (mismo nombre y tamaño) ya fue asignado a OTRA casilla diferente?
  for (const [otherKey, assigned] of Object.entries(assignedFiles)) {
    if (otherKey !== typeKey && assigned.name === file.name && assigned.size === file.size) {
      const otherMeta = FILE_METADATA[otherKey] || { label: otherKey };
      box.className = "mt-3 p-3.5 rounded-lg text-xs accent-critical space-y-2";
      box.style.backgroundColor = "var(--status-critical-bg)";
      box.innerHTML = "";

      const statusTitle = el("div", { class: "font-semibold flex items-center gap-1.5" }, [
        el("span", { style: "color: var(--status-critical)" }, "Error: Archivo duplicado"),
      ]);

      const explanation = el("p", { class: "text-slate-800" }, [
        "El archivo ",
        el("strong", {}, `"${file.name}"`),
        " ya fue asignado a la casilla de ",
        el("strong", {}, `"${otherMeta.label}"`),
        ". Cada una de las 7 casillas requiere su propio archivo de datos. Por favor seleccione el archivo correcto."
      ]);

      box.append(statusTitle, explanation);
      btn.disabled = true;
      reason.textContent = `Deshabilitado: ya asignado a ${otherMeta.label}`;
      return;
    }
  }

  // 2. VALIDACIÓN DE DUPLICADO EN LA MISMA CASILLA:
  const isAlreadySavedHere = assignedFiles[typeKey] &&
    assignedFiles[typeKey].name === file.name &&
    assignedFiles[typeKey].size === file.size;

  try {
    const headerLine = await readHeaderLine(file);
    const parsed = parseHeader(headerLine);
    const expected = EXPECTED_COLUMNS[typeKey] || [];
    const meta = FILE_METADATA[typeKey] || { label: typeKey };

    // Comparar columnas (insensible a mayúsculas/minúsculas para nombres y espacios recortados)
    const expectedNorm = expected.map(c => c.trim().toLowerCase());
    const foundNorm = parsed.columns.map(c => c.trim().toLowerCase());

    const missing = expected.filter(c => !foundNorm.includes(c.trim().toLowerCase()));
    const unexpected = parsed.columns.filter(c => !expectedNorm.includes(c.trim().toLowerCase()));

    const isMatch = missing.length === 0;

    box.innerHTML = "";

    if (isMatch) {
      box.className = "mt-3 p-3.5 rounded-lg text-xs accent-ok space-y-2";
      box.style.backgroundColor = "var(--status-ok-bg)";

      const statusTitle = el("div", { class: "font-semibold flex items-center gap-1.5" }, [
        el("span", { style: "color: var(--status-ok)" }, `Estructura válida para "${meta.label}"`),
        el("span", { class: "text-slate-500 font-normal ml-2" }, `(${parsed.columns.length} columnas detectadas)`)
      ]);

      const colsPreview = el("div", { class: "flex flex-wrap gap-1 mt-1" },
        parsed.columns.map(c => el("span", { class: "px-2 py-0.5 rounded text-[11px] bg-white border border-emerald-200 text-emerald-800" }, c))
      );

      box.append(statusTitle, colsPreview);

      if (isAlreadySavedHere) {
        const alreadyNotice = el("div", { class: "mt-1.5 text-emerald-800 font-medium flex items-center gap-1" }, [
          `Este archivo ya se encuentra confirmado para esta casilla (asignado a las ${assignedFiles[typeKey].assignedAt}).`
        ]);
        box.append(alreadyNotice);
        btn.disabled = true;
        reason.textContent = "Archivo ya confirmado";
      } else {
        btn.disabled = false;
        reason.textContent = "Listo para confirmar";
      }
    } else {
      box.className = "mt-3 p-3.5 rounded-lg text-xs accent-warning space-y-2";
      box.style.backgroundColor = "var(--status-warning-bg)";

      const statusTitle = el("div", { class: "font-semibold flex items-center gap-1.5" }, [
        el("span", { style: "color: var(--status-warning)" }, `Conflicto de columnas para "${meta.label}"`),
        el("span", { class: "text-slate-600 font-normal ml-2" }, "(Archivo equivocado)")
      ]);

      const explanation = el("p", { class: "text-slate-700" },
        "El archivo seleccionado no coincide con la estructura requerida para esta casilla. Verifique si seleccionó un archivo de otra categoría."
      );

      const detailsList = el("div", { class: "space-y-1.5 mt-2" });

      if (missing.length > 0) {
        detailsList.appendChild(el("div", { class: "text-red-700" }, [
          el("strong", {}, `Columnas obligatorias que le faltan (${missing.length}): `),
          missing.join(", ")
        ]));
      }

      if (unexpected.length > 0) {
        detailsList.appendChild(el("div", { class: "text-amber-800" }, [
          el("strong", {}, `Columnas inesperadas que trae (${unexpected.length}): `),
          unexpected.slice(0, 8).join(", ") + (unexpected.length > 8 ? "..." : "")
        ]));
      }

      box.append(statusTitle, explanation, detailsList);
      btn.disabled = true;
      reason.textContent = `Deshabilitado: faltan ${missing.length} columnas obligatorias`;
    }
  } catch (err) {
    box.className = "mt-3 p-3.5 rounded-lg text-xs accent-critical space-y-1";
    box.style.backgroundColor = "var(--status-critical-bg)";
    box.innerHTML = `<p class="font-semibold text-red-700">Error al leer el archivo: ${err.message}</p>`;
    btn.disabled = true;
    reason.textContent = "Error de lectura";
  }
}

/**
 * Lee los primeros 8 KB del archivo para extraer la primera línea sin cargar gigabytes en memoria.
 */
function readHeaderLine(file) {
  return new Promise((resolve, reject) => {
    const slice = file.slice(0, 8192);
    const reader = new FileReader();
    reader.onload = (e) => {
      const text = e.target.result;
      const firstLine = text.split(/\r\n|\r|\n/)[0];
      if (!firstLine || !firstLine.trim()) {
        reject(new Error("El archivo está vacío o la primera línea no contiene datos"));
      } else {
        resolve(firstLine);
      }
    };
    reader.onerror = () => reject(new Error("No se pudo leer el archivo seleccionado"));
    reader.readAsText(slice, "utf-8");
  });
}

/**
 * Detecta el delimitador con mayor frecuencia entre |, ;, \t y ,
 */
function parseHeader(line) {
  let bestDelim = "|";
  let maxCount = -1;

  for (const d of DELIMITERS) {
    const count = (line.match(new RegExp("\\" + d, "g")) || []).length;
    if (count > maxCount) {
      maxCount = count;
      bestDelim = d;
    }
  }

  const columns = line
    .split(bestDelim)
    .map(c => c.trim().replace(/^["']|["']$/g, ""))
    .filter(c => c.length > 0);

  return {
    delimiter: bestDelim,
    columns
  };
}
