# Asistente IA de Gestión Hospitalaria — HSLV

MVP para el **Hospital Susana López de Valencia** (Popayán) desarrollado en el Hackathon Campus Party FUP 2026.
Directivos y jefes de servicio preguntan en lenguaje natural sobre la operación del hospital y reciben
**respuesta + tabla/gráfico + recomendación**, junto con un **dashboard de KPIs** y **alertas automáticas**.

## El reto

El hospital atiende ~500 pacientes diarios, pero la información de camas, tiempos de espera, quirófanos,
medicamentos y citas está dispersa en sistemas y hojas de cálculo desconectadas. Los directivos dependen de
reportes manuales a TI, lo que retrasa decisiones críticas.

**Nuestra solución:** un agente NL2SQL que convierte preguntas en consultas SQL seguras sobre una base
unificada, con un plan B por reglas para que la demo nunca se caiga.

## Cómo ejecutar

```bash
# 1. Entorno
python -m venv .venv
.venv\Scripts\activate            # Windows  (Linux/macOS: source .venv/bin/activate)
pip install -r requirements.txt

# 2. Credenciales
copy .env.example .env            # completar LLM_PROVIDER, la API key y AUTH_* (ver abajo)

# 3. Base de datos (~20 s)
#    Los 7 .txt crudos del HIS NO están en el repo: copiarlos en DATOS/ antes de este paso
python etl/build_db.py --raw "DATOS" --out data/hospital.db

# 4. Aplicación
uvicorn app.main:app --reload     # http://localhost:8000

#    La primera carga de KPIs tarda ~20 s (se precalienta sola al arrancar); después es instantánea.

# 5. Pruebas (guard SQL, agente, login, KPIs, alertas y las 4 preguntas de la demo)
python -m pytest -q
```

### Variables de entorno (`.env`)

| Variable | Uso | Default |
|----------|-----|---------|
| `LLM_PROVIDER` | `anthropic` \| `openai` \| `none` (solo reglas) | `none` |
| `LLM_MODEL` | Modelo a usar (opcional) | `claude-sonnet-5` / `gpt-4o-mini` |
| `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` | Clave del proveedor | — |
| `DB_PATH` | Base SQLite | `data/hospital.db` |
| `AUTH_USERNAME` | Usuario del panel (acepta también `usuario@hosusana.gov.co`) | `admin` |
| `AUTH_PASSWORD` | Contraseña del panel | `hslv2026` (**solo demo**, cámbiela) |
| `AUTH_SECRET` | Clave para firmar los tokens JWT (32+ caracteres aleatorios) | se genera al arrancar |

| `ACCESS_PATH` | Archivo de usuarios y matriz de permisos | `data/access.json` |

Sin `AUTH_SECRET`, los tokens dejan de valer al reiniciar el servidor (hay que volver a iniciar sesión).

### Permisos por rol

| Rol | Acceso por defecto |
|-----|--------------------|
| **Gerencia / Dirección** | Todos los módulos + pestaña **Permisos** (usuarios y matriz rol × módulo) |
| **Jefe de servicio** | Dashboard, Ocupación, Asistente IA, Alertas y Medicamentos; queda asociado a un servicio |

El usuario del `.env` es siempre Dirección. Desde **Permisos** crea usuarios (contraseña con hash PBKDF2),
los activa o desactiva, les cambia el rol y marca qué módulos ve cada rol. Los cambios aplican de inmediato:
el backend responde 403 a los módulos no permitidos y el panel oculta sus pestañas.

## Documentación

| Documento | Contenido |
|-----------|-----------|
| [docs/01-arquitectura.md](docs/01-arquitectura.md) | Componentes, flujo del agente, contrato API, patrones, seguridad |
| [docs/02-tecnologias.md](docs/02-tecnologias.md) | Stack y justificación de cada tecnología |
| [docs/03-metodologia.md](docs/03-metodologia.md) | Roles, cronograma por sprints, flujo Git, DoD, riesgos |
| [CLAUDE.md](CLAUDE.md) | Contexto técnico completo: esquema de datos, KPIs, reglas del agente |

## Tecnologías

Python 3.11+ · pandas · SQLite · FastAPI · Anthropic / OpenAI · HTML + Tailwind · Chart.js · GitHub Projects

## Preguntas de la demo

| # | Pregunta |
|---|----------|
| 1 | ¿Cuántas camas de UCI están ocupadas hoy? |
| 2 | ¿Cuáles son los medicamentos con menos de 5 días de inventario? |
| 3 | ¿Cuál es el tiempo de espera promedio en urgencias en la última semana? |
| 4 | ¿Qué servicio tiene más pacientes ingresados este mes? |

## Equipo

| Integrante | Rol | Aportes |
|------------|-----|---------|
| _(nombre)_ | Agente IA / Backend | |
| _(nombre)_ | Datos, KPIs y Alertas | |
| _(nombre)_ | Frontend y Presentación | |

## Limitaciones

Inventario de medicamentos simulado (consumo real), capacidad de camas estimada, cirugías sin fecha ni quirófano
y datos hasta el 21 de septiembre de 2026. Detalle en [docs/01-arquitectura.md](docs/01-arquitectura.md#8-limitaciones-conocidas-se-dicen-en-la-demo).
