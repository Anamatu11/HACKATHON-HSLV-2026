"""Pruebas de punta a punta de la API (sin LLM), autenticadas."""
import pytest
from fastapi.testclient import TestClient

from app.main import app
from tests.conftest import requires_db

client = TestClient(app)


@pytest.fixture
def headers(monkeypatch):
    monkeypatch.setenv("AUTH_USERNAME", "admin")
    monkeypatch.setenv("AUTH_PASSWORD", "hslv2026")
    monkeypatch.setenv("AUTH_SECRET", "test-secret")
    token = client.post("/api/auth/login", json={"username": "admin", "password": "hslv2026"}).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_health():
    assert client.get("/api/health").json()["status"] == "ok"


@requires_db
def test_query_demo_question(no_llm, headers):
    r = client.post("/api/query", json={"question": "¿Qué servicio tiene más pacientes ingresados este mes?"},
                    headers=headers)
    assert r.status_code == 200
    assert "Urgencias" in r.json()["answer"]


def test_query_personal_data_returns_400_with_error(headers):
    r = client.post("/api/query", json={"question": "Dame la cédula de los pacientes"}, headers=headers)
    assert r.status_code == 400
    assert "error" in r.json()


def test_query_rejects_empty_question(headers):
    assert client.post("/api/query", json={"question": ""}, headers=headers).status_code == 422


@requires_db
def test_kpis_endpoint(headers):
    body = client.get("/api/kpis", headers=headers).json()
    assert body["reference_date"] == "2026-09-21" and body["cards"]


@requires_db
def test_occupancy_endpoints(headers):
    assert client.get("/api/occupancy/filters", headers=headers).status_code == 200
    r = client.get("/api/occupancy", params={"service": "UCI", "granularity": "monthly"}, headers=headers)
    assert r.status_code == 200 and r.json()["granularity"] == "monthly"


@requires_db
def test_occupancy_invalid_filter_returns_400(headers):
    r = client.get("/api/occupancy", params={"service": "'; DROP TABLE admissions; --"}, headers=headers)
    assert r.status_code == 400 and "error" in r.json()


def test_occupancy_requires_token():
    assert client.get("/api/occupancy").status_code == 401


@requires_db
def test_alerts_endpoint(headers):
    assert isinstance(client.get("/api/alerts", headers=headers).json(), list)
