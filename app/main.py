"""
API FastAPI + servidor de los estáticos del frontend.

Responsable: Rol A (integrador). Cambios cortos y avisados: es el único archivo compartido.

Ejecutar desde la raíz del repo:
    uvicorn app.main:app --reload      ->  http://localhost:8000  (docs en /docs)

Rutas (contrato completo en docs/01-arquitectura.md §3):
    POST /api/query   -> agent.answer_question()
    GET  /api/kpis    -> kpis.get_kpis()
    GET  /api/alerts  -> alerts.get_alerts()
    GET  /api/health  -> estado de la BD y del proveedor LLM
    /                 -> web/ (index.html, app.js)
"""
import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

load_dotenv()

from app import alerts, kpis  # noqa: E402  (después de load_dotenv para que lean el .env)
from app.agent import agent  # noqa: E402

WEB_DIR = Path(__file__).resolve().parent.parent / "web"

app = FastAPI(title="HSLV - Asistente IA de Gestión Hospitalaria", version="0.1.0")


class QueryRequest(BaseModel):
    question: str = Field(..., min_length=3, max_length=500)


@app.get("/api/health")
def health() -> dict:
    # TODO (Rol A): verificar la BD con db.get_reference_date() y devolver "db": True/False
    return {"status": "ok", "llm_provider": os.getenv("LLM_PROVIDER", "none")}


@app.post("/api/query")
def query(req: QueryRequest) -> dict:
    try:
        return agent.answer_question(req.question)
    except NotImplementedError:
        raise HTTPException(status_code=501, detail="Agente aún no implementado")


@app.get("/api/kpis")
def get_kpis() -> dict:
    try:
        return kpis.get_kpis()
    except NotImplementedError:
        raise HTTPException(status_code=501, detail="KPIs aún no implementados")


@app.get("/api/alerts")
def get_alerts() -> list[dict]:
    try:
        return alerts.get_alerts()
    except NotImplementedError:
        raise HTTPException(status_code=501, detail="Alertas aún no implementadas")


# Se monta al final para que /api/* tenga prioridad. html=True sirve index.html en "/".
if WEB_DIR.exists():
    app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")
