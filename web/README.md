# web/ — Frontend

HTML + Tailwind (CDN) + Chart.js (CDN) con módulos ES nativos, sin framework ni build step.
FastAPI sirve esta carpeta en `/` y la API en `/api/*` (mismo origen, sin CORS).

## Archivos

| Archivo | Contenido |
|---------|-----------|
| `index.html` | Login real contra `POST /api/auth/login` (JWT). Logo oficial sobre blanco, lema institucional |
| `dashboard.html` | Esqueleto del panel: pestañas Resumen · Asistente IA · Alertas · Medicamentos |
| `css/styles.css` | Tokens de marca y de gráficos (paleta validada), estados, tablas |
| `js/api.js` | Cliente de la API: guarda el token, lo envía como `Bearer`, redirige al login ante un 401 |
| `js/ui.js` | Helper `el()` (inserta texto con `textContent`, nunca `innerHTML`), formato es-CO, tablas, etiquetas de estado |
| `js/charts.js` | Fábrica de gráficos Chart.js: paleta fija, línea de meta, un solo eje, leyenda solo con ≥ 2 series |
| `js/dashboard.js` | Tarjetas KPI, 9 gráficos, alertas con filtros, inventario con buscador |
| `js/chat.js` | Chat con el agente: respuesta, gráfico, tabla, SQL en `<details>`, recomendaciones |
| `assets/logo-hospital.png` | Logo oficial con sello de acreditación (no alterar: Manual de Identidad 2026) |

## Identidad visual (Manual de Marca HSLV 2026)

- Colores: verde `#76b82a`, verde oscuro `#327531`, azul marino `#29235c`, blanco.
- El logo va siempre sobre fondo blanco, sin deformar ni cambiar colores, acompañado del sello de acreditación.
- Lema: *¡Pensando en ti, doy lo mejor de mí!*
- Gráficos: paleta `#327531 · #2a78d6 · #eb6834 · #4a3aa7`, validada para daltonismo y contraste.
  Los colores de estado (normal/atención/crítico) siempre llevan icono y texto.

## Accesibilidad

Cada gráfico tiene un botón **Ver tabla**; los estados nunca dependen solo del color; foco visible con teclado;
responsive desde 360 px.
