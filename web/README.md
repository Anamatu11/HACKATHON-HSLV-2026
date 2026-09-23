# web/ — Frontend

**Responsable:** Rol C. HTML + Tailwind (CDN) + Chart.js (CDN), sin framework ni build step.

## Archivos que van aquí

| Archivo | Contenido |
|---------|-----------|
| `index.html` | Login de demo, identidad HSLV, 4 KPI, gráficos (ocupación UCI, quirófanos, ingresos por servicio), alertas, chat, tabla de medicamentos con buscador |
| `app.js` | Lógica, `mockData`, gráficos Chart.js y chat |

## Cómo se sirve

FastAPI monta esta carpeta en `/` (`app/main.py`). Con `uvicorn app.main:app --reload` la página queda en
`http://localhost:8000` y la API en `/api/*` (mismo origen, sin CORS).

## Integración con el backend

El `mockData` de `app.js` **es el contrato**: el backend devuelve exactamente esa forma.
Integrar = reemplazar cada mock por un `fetch`, en un solo lugar:

| Componente | Endpoint |
|------------|----------|
| 4 KPI, gráficos, tabla de medicamentos | `GET /api/kpis` |
| Panel de alertas | `GET /api/alerts` |
| Chat (respuesta, tabla, gráfico, SQL en `<details>`, recomendaciones) | `POST /api/query` con `{ "question": "..." }` |

## Login

`admin` / `hslv2026` es una **pantalla de acceso de demostración**, no seguridad real (la clave está en `app.js`
y el repo es público). Así se debe presentar en la demo.
