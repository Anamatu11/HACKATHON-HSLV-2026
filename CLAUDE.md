# CLAUDE.md — Asistente IA de Gestión Hospitalaria (Hackathon Campus Party FUP 2026)

Este archivo es tu contexto principal. Léelo completo antes de escribir código.
Idioma de trabajo con el equipo: **español**. Código (variables, funciones, tablas): **inglés**.

---

## 1. El reto en una frase

Construir en **~8 horas de trabajo efectivo** un **MVP funcional** para el Hospital Susana López de
Valencia (HSLV, Popayán; mediana complejidad, fuerte en gineco-obstetricia, pediatría y UCI neonatal)
donde directivos y jefes de servicio **pregunten en lenguaje natural** sobre los datos del hospital y
reciban **respuesta + tabla/gráfico + recomendación**, acompañado de un **dashboard de KPIs**.

El corazón es el **agente NL2SQL**. El dashboard es el complemento. Todo debe poder demostrarse en vivo.

### Lo que evalúan (según el PDF del reto)
1. Agente conversacional (NL2SQL) que responde preguntas reales.
2. Dashboard con KPIs: ocupación, tiempos de espera, eficiencia de quirófanos, rotación de
   medicamentos, demanda de servicios/especialidades.
3. Carga y análisis de datos históricos.
4. Recomendaciones/alertas automáticas (desabastecimiento, reasignar personal/abrir camas,
   programación de cirugías). Valor añadido: alertas predictivas y análisis de causa raíz.
5. Seguridad: sin datos personales en respuestas, `.env` para credenciales, SQL saneado.
6. Repo en GitHub con README (reto, cómo ejecutar, tecnologías, roles/autores), código modular.

### Las 4 preguntas de la demo (DEBEN funcionar perfecto)
| # | Pregunta | Respuesta esperada con la BD actual |
|---|---|---|
| 1 | ¿Cuántas camas de UCI están ocupadas hoy? | 27 de 46 (58,7%); 73% sobre camas físicas (37) |
| 2 | ¿Cuáles son los medicamentos con menos de 5 días de inventario? | 35 medicamentos (inventario **simulado**) |
| 3 | ¿Cuál es el tiempo de espera promedio en urgencias en la última semana? | 58,6 min (888 atenciones); desglosar por triage |
| 4 | ¿Qué servicio tiene más pacientes ingresados este mes? | Urgencias (1.169), luego Pediatría (409) y Hosp. Adultos (401) |

"Hoy" = `dataset_meta.reference_date` = **2026-09-21** (último día con ingresos). Nunca uses `date('now')`.

---

## 2. Stack (decidido; no cambiar sin consultar al equipo)

- **Datos:** SQLite `data/hospital.db`, generada por `etl/build_db.py`.
- **Backend:** Python 3.11 + **FastAPI**.
- **Agente:** LLM con proveedor intercambiable por variable de entorno `LLM_PROVIDER`
  (`anthropic` | `openai`) + **plan B por reglas** (diccionario de preguntas → SQL) si no hay API/red.
- **Frontend:** HTML + Tailwind (CDN) + **Chart.js**, servido por FastAPI como estáticos
  (el equipo domina web). Alternativa aceptada por el reto: Streamlit.
- **Despliegue opcional:** Render/Railway. Lo obligatorio es que corra local con instrucciones claras.

### Estructura de carpetas objetivo
```
HACKATHON-HSLV-2026/     # raíz del repo
├── CLAUDE.md
├── README.md
├── .gitignore
├── DATOS/                # .txt crudos (NO se suben a git) + PDFs del reto
├── docs/                 # arquitectura, tecnologías, metodología
├── requirements.txt
├── .env.example          # LLM_PROVIDER, ANTHROPIC_API_KEY, OPENAI_API_KEY, DB_PATH
├── data/hospital.db      # NO se sube a git (~260 MB, GitHub rechaza >100 MB; se regenera con el ETL)
├── etl/build_db.py       # YA EXISTE y está validado
├── app/                  # Backend (roles A y B)
│   ├── __init__.py
│   ├── main.py           # FastAPI: rutas /api/* + sirve web/ como estáticos
│   ├── db.py             # conexión SQLite solo-lectura (timeout por consulta)
│   ├── auth.py           # login con .env + JWT               → POST /api/auth/login, GET /api/auth/me
│   ├── formatting.py     # cifras en formato es-CO (1.169 · 58,7)
│   ├── kpis.py           # consultas del dashboard (cacheadas) → GET /api/kpis
│   ├── alerts.py         # alertas + recomendaciones + predictiva → GET /api/alerts
│   └── agent/
│       ├── __init__.py
│       ├── agent.py           # orquesta: pregunta → SQL → ejecuta → respuesta → POST /api/query
│       ├── fallback.py        # preguntas frecuentes → SQL fijo (plan B)
│       ├── sql_guard.py       # validación/saneamiento del SQL
│       ├── schema_prompt.py   # esquema + reglas + few-shot para el LLM
│       └── llm.py             # cliente Anthropic/OpenAI (factory)
├── web/                  # Frontend conectado a la API real (detalle en web/README.md)
│   ├── index.html        # login JWT con identidad HSLV
│   ├── dashboard.html    # pestañas: Resumen · Asistente IA · Alertas · Medicamentos
│   ├── css/styles.css    # tokens de marca + paleta de gráficos validada
│   ├── js/               # api.js, ui.js, charts.js, dashboard.js, chat.js (módulos ES)
│   └── assets/           # logo oficial con sello de acreditación
└── tests/                # guard SQL, agente (LLM falso), API, login, KPIs, alertas, 4 preguntas demo
```

**Frontend (`web/`)**: HTML + Tailwind (CDN) + Chart.js (CDN), sin framework ni build step. Sigue el Manual de
Marca HSLV 2026 (verde `#76b82a`, verde oscuro `#327531`, azul `#29235c`; logo siempre sobre blanco, sin alterar,
con sello de acreditación; lema "¡Pensando en ti, doy lo mejor de mí!"). Todo texto de la API se inserta con
`textContent` (nunca `innerHTML`).

### Endpoints mínimos
- `POST /api/query` `{question}` → `{answer, sql, columns, rows, chart, recommendations}`
- `GET /api/kpis` → tarjetas + series para gráficos
- `GET /api/alerts` → lista de alertas activas
- `GET /api/health`

---

## 3. Datos — REGLA DE ORO

**Nunca leas los `.txt` crudos desde la app.** Toda la app y el agente consultan `data/hospital.db`.
Si falta un dato o una columna, se agrega en `etl/build_db.py` y se regenera la BD:

```bash
python etl/build_db.py --raw DATOS --out data/hospital.db   # ~20 s
```

### Suciedad del crudo que el ETL ya resuelve (no la vuelvas a "arreglar")
- `Triage.txt`: 1.675 filas vacías (ingresos sin triage) → eliminadas. Cruzar sin eliminarlas multiplica filas (NaN×NaN).
- Comillas sueltas en texto libre → se lee con `quoting=csv.QUOTE_NONE`.
- Signos vitales como texto, con valores imposibles (temperatura 3636, 0.36) → numéricos + rangos válidos, fuera de rango = NULL.
- Categorías duplicadas en `risk_type` ("Accidente de transito" / "Accidente de Transito Comun") → unificadas.
- 24 etiquetas de triage → `triage_level` (1–4) + `triage_area` (Adultos/Pediatría/Ginecología).
- Nombres de grupo de cama → `service` legible (Urgencias, UCI, Pediatría...).
- Ceros a la izquierda en `schedule_id`; espacios dobles; fechas → texto ISO `YYYY-MM-DD HH:MM:SS`.
- Se eliminan `NombrePaciente` y `MotivoConsulta` (datos personales/texto libre).
- El archivo crudo NO viene ordenado por fecha.

### Esquema de `hospital.db`

**Tablas base (limpias)**

| Tabla | Filas | Grano | Columnas clave |
|---|---|---|---|
| `patients` | 14.502 | paciente | patient_id PK, document_type, sex, birth_date, insurer, regime (Contributivo/Subsidiado…), department, municipality, zone |
| `admissions` | 17.781 | ingreso/episodio (**tabla central**) | admission_id PK, admission_number, patient_id FK, admission_class (Ambulatorio = urgencias sin hospitalizar / Hospitalario), admission_route, risk_type, admission_at, hospitalization_at, triage_id FK, bed_code, bed_name, is_virtual_bed, service, sub_service, diagnosis_code (CIE-10), diagnosis_name, diagnosis_chapter (letra CIE-10), age_years, age_group, last_activity_at, length_of_stay_days |
| `triage` | 16.106 | evento de triage | triage_id PK, patient_id, triage_at, triage_code, triage_label, triage_level (1=emergencia…4), triage_area, systolic_bp, diastolic_bp, heart_rate, respiratory_rate, temperature_c |
| `first_care` | 17.375 | ingreso | admission_id PK/FK, first_care_at (primera atención médica) |
| `services` | 582.357 | línea de servicio prestado | line_id PK, admission_id FK, service_code (CUPS), service_name, quantity, performed_at, area_code, area (p.ej. "QUIROFANOS - CIRUGIA GENERAL", "APOYO DIAGNOSTICO - LABORATORIO CLINICO"), specialty |
| `medications` | 579.465 | línea dispensada | line_id PK, admission_id FK, item_code, item_name, item_type ('Medicamento' si código ATC / 'Dispositivo/Insumo'), quantity, dispensed_at, area, specialty |
| `surgery_schedule` | 13.046 | procedimiento programado | schedule_id (agrupa una cirugía), patient_id, admission_id (nullable), procedure_code, in_dataset (1 si el ingreso existe en admissions), was_billed (1 si el procedimiento aparece cobrado en services para ese ingreso ⇒ realizada) |

**Tablas derivadas (calculadas en el ETL)**

| Tabla/Vista | Qué es |
|---|---|
| `wait_times` | Por ingreso con triage: service, triage_level, triage_area, triage_at, first_care_at, **wait_minutes** = first_care_at − triage_at (filtrado 0–1440 min) |
| `bed_census_daily` | census_date, service, occupied_beds: pacientes presentes a las 12:00 (entre hospitalization_at y last_activity_at) |
| `bed_capacity` | service, capacity_beds (camas distintas usadas), physical_beds (sin virtuales), is_estimated=1 |
| `v_occupancy_daily` | census + capacidad: occupancy_pct, occupancy_physical_pct (>100% = sobreocupación con camas virtuales) |
| `stays` | Líneas INTERNACIÓN facturadas: admission_id, unit (UCI Neonatal, UCI Adultos, Intermedio…), start_at, days, end_at_estimated. Úsala para estancia por unidad de cuidado, **no** para ocupación de "hoy" (se factura al egreso) |
| `drug_inventory` | **SIMULADO** (semilla fija): item_code, item_name, avg_daily_consumption (real, últimos 30 días), stock_units, days_of_inventory, expiry_date, is_simulated=1 |
| `v_admissions_safe` | Ingresos sin patient_id ni diagnóstico específico (solo capítulo CIE-10) |
| `dataset_meta` | key/value: reference_date, data_start, notas de estimación |

### Relaciones
```
patients 1─N admissions (patient_id)          admissions N─1 triage (triage_id)
admissions 1─1 first_care (admission_id)      admissions 1─N services / medications (admission_id)
admissions 1─N surgery_schedule (admission_id, solo si in_dataset=1)
admissions 1─1 wait_times / 1─N stays (admission_id)
```
Un paciente puede tener varios ingresos (17% tiene >1). Periodo: 2026-05-01 → 2026-09-21.

### Limitaciones que hay que DECIR en la demo (no esconder)
- **Inventario simulado**: los datos no traen stock ni vencimiento. `avg_daily_consumption` sí es real.
- **Capacidad estimada** por camas distintas observadas; reemplazable por la real.
- **Servicio del ingreso = cama registrada** (probablemente la actual/última). Los traslados internos no se ven,
  así que la ocupación histórica de UCI está subestimada; la de "hoy" es la más confiable.
- **Cirugías**: sin fecha ni quirófano; solo el 31% cruza con ingresos. "Realizada" = procedimiento cobrado.
  253 ingresos tienen >1 programación (posibles reprogramaciones).
- Septiembre está incompleto (hasta el 21).

---

## 4. Definiciones de KPIs (SQL de referencia, SQLite)

Usa siempre `REF = (SELECT value FROM dataset_meta WHERE key='reference_date')`.

```sql
-- Ocupación hoy por servicio
SELECT service, occupied_beds, capacity_beds, occupancy_pct, occupancy_physical_pct
FROM v_occupancy_daily WHERE census_date = (SELECT value FROM dataset_meta WHERE key='reference_date');

-- Ocupación promedio mensual por servicio
SELECT substr(census_date,1,7) AS month, service, ROUND(AVG(occupancy_pct),1) AS avg_occupancy_pct
FROM v_occupancy_daily GROUP BY 1,2;

-- Espera promedio por triage (últimos 7 días)
SELECT triage_level, COUNT(*) n, ROUND(AVG(wait_minutes),1) avg_wait_min
FROM wait_times
WHERE triage_at >= date((SELECT value FROM dataset_meta WHERE key='reference_date'),'-7 day')
GROUP BY triage_level;

-- Cirugías realizadas vs programadas (solo las que cruzan)
SELECT COUNT(DISTINCT schedule_id) scheduled,
       COUNT(DISTINCT CASE WHEN was_billed=1 THEN schedule_id END) performed
FROM surgery_schedule WHERE in_dataset=1;

-- Rotación de medicamentos (mayor/menor) en el mes
SELECT item_name, SUM(quantity) units FROM medications
WHERE item_type='Medicamento' AND substr(dispensed_at,1,7)='2026-09'
GROUP BY item_name ORDER BY units DESC LIMIT 10;   -- ASC para menor rotación

-- Demanda: especialidades más solicitadas
SELECT specialty, COUNT(DISTINCT admission_id) admissions FROM services GROUP BY 1 ORDER BY 2 DESC LIMIT 10;

-- Stock crítico
SELECT item_name, stock_units, avg_daily_consumption, days_of_inventory
FROM drug_inventory WHERE days_of_inventory < 5 ORDER BY days_of_inventory;
```
Otros KPIs útiles: estancia promedio (`length_of_stay_days` o `stays.days`), ingresos por día/hora
(heatmap de picos), % de uso de camas virtuales, reingresos (pacientes con >1 ingreso en 30 días),
principales diagnósticos por capítulo CIE-10, régimen/aseguradora.

---

## 5. Diseño del agente NL2SQL

Flujo: `pregunta → (fallback por reglas si coincide) → LLM genera SQL → sql_guard → ejecutar (solo lectura, timeout, LIMIT) → LLM redacta respuesta corta en español + sugiere gráfico → alerts.py añade recomendaciones`.

**Prompt del sistema del agente debe incluir:** el esquema de la sección 3 (solo tablas permitidas), la regla de
`reference_date`, las definiciones de la sección 4 como few-shot (mínimo las 4 preguntas de la demo),
y estas instrucciones: responder solo con un SELECT de SQLite; usar vistas derivadas antes que recalcular;
si la pregunta pide datos personales, negarse.

**`sql_guard.py` (obligatorio):**
- Solo una sentencia; debe empezar por `SELECT` o `WITH`. Rechazar `INSERT/UPDATE/DELETE/DROP/ALTER/ATTACH/PRAGMA/CREATE`.
- Abrir SQLite en modo solo lectura: `sqlite3.connect("file:data/hospital.db?mode=ro", uri=True)`.
- Forzar `LIMIT 200` si no hay LIMIT. Timeout de consulta.
- **Privacidad:** columnas prohibidas en el resultado: `patient_id`, `birth_date`, `diagnosis_name`, `diagnosis_code`,
  `bed_code`, `bed_name`. Si aparecen, rechazar o reescribir (agregados sí están permitidos: COUNT por diagnóstico
  agregado a capítulo CIE-10 está bien; listar pacientes con su diagnóstico no).
- Si el SQL falla, reintentar una vez enviando el error al LLM.

**Respuesta al frontend:** `answer` (1–3 frases con el número clave), `sql` (mostrarlo colapsable: da confianza al jurado),
`columns/rows`, `chart` (`{type: bar|line|pie|none, x, y}` elegido por reglas simples: serie temporal→line,
categorías≤8→bar/pie), `recommendations` (lista).

**Plan B (`fallback.py`):** diccionario con patrones/palabras clave → SQL fijo para las 4 preguntas de la demo y
~10 más (ocupación por servicio, espera por triage, top medicamentos, cirugías, demanda por especialidad).
Se activa si no hay API key, si el LLM falla o si la pregunta coincide exactamente. La demo nunca debe caerse.

---

## 6. Recomendaciones y alertas (`alerts.py`, reglas simples y explicables)

- **Desabastecimiento:** `days_of_inventory < 5` → "Reabastecer X: quedan N días (consumo diario Y)". Crítico si < 2.
- **Vencimiento:** `expiry_date` en ≤ 30 días con stock alto → "Priorizar uso / redistribuir".
- **Ocupación:** `occupancy_physical_pct ≥ 90` → "Abrir camas / habilitar expansión / reasignar personal a <servicio>".
  Si hay servicios < 60% en el mismo día, sugerir de dónde reasignar.
- **Tiempos de espera:** si la espera de triage 2 supera 30 min o la de triage 3 supera su promedio histórico en >20% →
  alerta, y **causa raíz**: comparar volumen por hora/turno (día 07–19, noche 19–07) y por triage_area contra el histórico.
- **Cirugías:** % no realizadas por semana/especialidad; ingresos con >1 programación = reprogramaciones.
- **Predictiva (valor añadido, si hay tiempo):** media móvil 7 días o regresión lineal simple de ingresos por
  servicio/diagnóstico → "se espera +X% en J (respiratorio) → aumentar stock de ..." (el hospital tiene picos respiratorios pediátricos).

---

## 7. Convenciones

- Código claro, comentado, nombres en inglés, módulos separados (agente / BD / API / frontend).
- Credenciales solo en `.env` (incluido en `.gitignore`, junto con `data/*.db` y los `.txt` crudos). Entregar `.env.example`.
- Commits pequeños y frecuentes; ramas `feature/*` → `main`.
- Antes de decir "listo": ejecutar las 4 preguntas de la demo contra `/api/query` y comparar con la tabla de la sección 1.
- No inventes columnas: si dudas, consulta `PRAGMA table_info(<tabla>)`.
- No reescribas el ETL sin avisar; si lo cambias, regenera la BD y vuelve a validar las 4 preguntas.

## 8. Orden de trabajo sugerido (prioridad de arriba a abajo)

1. `app/db.py` + `sql_guard.py` + `fallback.py` con las 4 preguntas → `/api/query` funcionando SIN LLM.
2. Integrar LLM (schema_prompt + few-shot) con reintento y fallback.
3. `/api/kpis` + dashboard (tarjetas: ocupación hoy, espera promedio, stock crítico, cirugías realizadas %;
   gráficos: ocupación diaria (línea), ingresos por servicio (barras/pastel), top medicamentos (barras)).
4. Chat en el frontend mostrando respuesta + tabla + gráfico + SQL + recomendaciones.
5. `alerts.py` y panel de alertas.
6. README, capturas, diagrama de arquitectura, ensayo de demo.
7. Extras solo si sobra tiempo: predicción, causa raíz, login JWT, despliegue.
