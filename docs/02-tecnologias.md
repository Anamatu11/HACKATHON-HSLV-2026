# Tecnologías y justificación

**Criterio único:** cada herramienta debe poder instalarse en minutos, correr local sin servidores externos
y ser dominada por el equipo. Lo que no cumple eso queda como mejora futura.

## Stack

| Capa | Tecnología | Versión | Por qué la elegimos | Alternativa descartada |
|------|-----------|---------|---------------------|------------------------|
| Lenguaje | Python | 3.11+ | Ecosistema de datos (pandas) y LLM en un solo lenguaje | — |
| ETL | pandas + numpy | ≥2.0 / ≥1.24 | Limpieza de ~1,2 M filas en ~20 s | Carga manual con `csv` |
| Base de datos | SQLite | incluida en Python | Sin servidor, archivo único, se regenera con un comando | PostgreSQL/Supabase: más setup sin beneficio en la demo |
| Backend | FastAPI + Uvicorn | ≥0.110 / ≥0.29 | Rápido, validación con Pydantic, docs automáticas en `/docs` | Flask: sin tipado ni docs automáticas |
| Agente IA | Anthropic SDK / OpenAI SDK | ≥0.40 / ≥1.30 | Proveedor intercambiable por `LLM_PROVIDER` | Un solo proveedor: punto único de falla |
| Plan B | Reglas en Python (`fallback.py`) | — | La demo funciona sin red ni API key | — |
| Frontend | HTML + Tailwind (CDN) + JavaScript | — | El equipo domina web; sin build step | Streamlit: rápido pero menos control visual |
| Gráficos | Chart.js (CDN) | 4.x | Línea, barras y pastel con poco código | Plotly: más pesado |
| Configuración | python-dotenv | ≥1.0 | Credenciales en `.env`, fuera del repo | Variables en código |
| Control de versiones | Git + GitHub | — | Exigido por el reto | — |
| Gestión | GitHub Projects (To Do / Doing / Done) | — | Vive junto al código y los PR | Trello: otra herramienta más |

## Modelos LLM

| Proveedor | Uso | Variable |
|-----------|-----|----------|
| `anthropic` | Principal: generación de SQL y redacción de respuesta | `ANTHROPIC_API_KEY` |
| `openai` | Respaldo si falla el principal o no hay cuota | `OPENAI_API_KEY` |
| `none` | Solo reglas (sin red) | — |

`temperature = 0` para generar SQL: queremos respuestas reproducibles, no creativas.

## Configuración (`.env`)

```dotenv
LLM_PROVIDER=anthropic        # anthropic | openai | none
ANTHROPIC_API_KEY=
OPENAI_API_KEY=
DB_PATH=data/hospital.db
```

## Herramientas de desarrollo

| Herramienta | Uso |
|-------------|-----|
| `venv` | Entorno aislado por persona |
| DB Browser for SQLite / extensión SQLite de VS Code | Explorar `hospital.db` y probar SQL |
| `/docs` de FastAPI | Probar endpoints sin frontend |
| `pytest` (opcional) | Pruebas de `sql_guard` y de las 4 preguntas de la demo |

## Mejoras futuras (se mencionan en la presentación)

- Modelo local (p. ej. SQLCoder) para no enviar el esquema a una API externa.
- Integración en tiempo real con la Historia Clínica Electrónica.
- Modelos de ML para predicción de demanda más precisos que la media móvil.
- PostgreSQL + login JWT con roles si se lleva a producción.
