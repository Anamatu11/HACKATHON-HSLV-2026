"""
API FastAPI + servidor de los estáticos del frontend.

Responsable: Rol A (integrador). Cambios cortos y avisados: es el único archivo compartido.

Ejecutar desde la raíz del repo:
    uvicorn app.main:app --reload      ->  http://localhost:8000  (docs en /docs)

Rutas (contrato completo en docs/01-arquitectura.md §3):
    POST /api/auth/login  -> token JWT (público)
    GET  /api/auth/me     -> usuario de la sesión + rol + módulos permitidos
    POST /api/query       -> agent.answer_question()   (módulo assistant)
    GET  /api/kpis        -> kpis.get_kpis()            (módulo dashboard o medications)
    GET  /api/alerts      -> alerts.get_alerts()        (módulo alerts)
    GET  /api/occupancy/filters, /api/occupancy -> occupancy.*  (módulo occupancy)
    /api/permissions, /api/users -> permissions.*       (módulo permissions: Dirección)
    GET  /api/health      -> estado de la BD y del proveedor LLM (público)
    /                     -> web/ (index.html = login, dashboard.html, assets)
"""
import logging
import os
import threading
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import Depends, FastAPI
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

load_dotenv()

from app import alerts, auth, db, kpis, occupancy, permissions  # noqa: E402  (después de load_dotenv para que lean el .env)
from app.agent import agent  # noqa: E402

WEB_DIR = Path(__file__).resolve().parent.parent / "web"
logger = logging.getLogger(__name__)


def warm_up_caches() -> None:
    """Calcula KPIs y alertas una vez (consultas pesadas) para que el dashboard cargue al instante."""
    try:
        kpis.get_kpis()
        alerts.get_alerts()
        logger.info("Caché de KPIs y alertas lista")
    except Exception as e:  # sin BD la app igual arranca; /api/health lo reporta
        logger.error("No se pudo precalentar la caché: %s", e)


@asynccontextmanager
async def lifespan(_: FastAPI):
    threading.Thread(target=warm_up_caches, daemon=True).start()   # no bloquea el arranque
    yield


app = FastAPI(title="HSLV - Asistente IA de Gestión Hospitalaria", version="0.2.0", lifespan=lifespan)
app.include_router(auth.router)
app.include_router(permissions.router)
allow = permissions.require_permission


class QueryRequest(BaseModel):
    question: str = Field(..., min_length=3, max_length=500)


@app.get("/api/health")
def health() -> dict:
    try:
        reference_date, db_ok = db.get_reference_date(), True
    except Exception:
        reference_date, db_ok = None, False
    return {"status": "ok", "db": db_ok, "reference_date": reference_date,
            "llm_provider": os.getenv("LLM_PROVIDER", "none")}


@app.exception_handler(agent.AgentError)
def agent_error_handler(_, exc: agent.AgentError) -> JSONResponse:
    # Contrato: errores esperados -> 400 {"error": mensaje para el usuario}
    return JSONResponse(status_code=400, content={"error": str(exc)})


@app.post("/api/query")
def query(req: QueryRequest, _user: dict = Depends(allow("assistant"))) -> dict:
    return agent.answer_question(req.question)


@app.get("/api/kpis")
def get_kpis(_user: dict = Depends(allow("dashboard", "medications"))) -> dict:
    return kpis.get_kpis()


@app.get("/api/alerts")
def get_alerts(_user: dict = Depends(allow("alerts"))) -> list[dict]:
    return alerts.get_alerts()


@app.get("/api/occupancy/filters")
def get_occupancy_filters(_user: dict = Depends(allow("occupancy"))) -> dict:
    return occupancy.get_filters()


@app.get("/api/occupancy")
def get_occupancy(service: str | None = None, sub_service: str | None = None, specialty: str | None = None,
                  granularity: str = "daily", start: str | None = None, end: str | None = None,
                  _user: dict = Depends(allow("occupancy"))):
    try:
        return occupancy.get_occupancy(service or None, sub_service or None, specialty or None,
                                       granularity, start or None, end or None)
    except ValueError as e:   # filtro inválido -> 400 con mensaje claro
        return JSONResponse(status_code=400, content={"error": str(e)})


# Se monta al final para que /api/* tenga prioridad. html=True sirve index.html en "/".
if WEB_DIR.exists():
    app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")
