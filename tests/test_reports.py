"""Especificación del informe PDF con auditoría (exclusivo de Gerencia / Dirección)."""
import json

import pytest
from fastapi.testclient import TestClient

from app import audit
from app.main import app
from tests.conftest import requires_db

client = TestClient(app)
DEMO_QUESTION = "¿Qué servicio tiene más pacientes ingresados este mes?"


@pytest.fixture(autouse=True)
def credentials(monkeypatch):
    monkeypatch.setenv("AUTH_USERNAME", "admin")
    monkeypatch.setenv("AUTH_PASSWORD", "hslv2026")
    monkeypatch.setenv("AUTH_SECRET", "test-secret-hslv-2026-very-secure-32-bytes")


def headers_for(username, password):
    r = client.post("/api/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture
def director():
    return headers_for("admin", "hslv2026")


def create_user(director, username, role, service=None):
    body = {"username": username, "name": f"Usuario {username}", "role": role, "password": "clave-segura-1"}
    if service:
        body["service"] = service
    assert client.post("/api/users", headers=director, json=body).status_code == 201
    return headers_for(username, "clave-segura-1")


def ask(headers, question=DEMO_QUESTION):
    return client.post("/api/query", json={"question": question}, headers=headers)


def test_reports_module_is_director_only_by_default(director):
    head = create_user(director, "jefe.uci", "service_head", "UCI")
    assert "reports" in client.get("/api/auth/me", headers=director).json()["permissions"]
    assert "reports" not in client.get("/api/auth/me", headers=head).json()["permissions"]


def test_matrix_cannot_grant_reports_to_service_head(director):
    client.put("/api/permissions", headers=director, json={"matrix": {"service_head": {"reports": True}}})
    matrix = client.get("/api/permissions", headers=director).json()["matrix"]
    assert matrix["service_head"]["reports"] is False


@requires_db
def test_query_is_audited_and_returns_query_id(no_llm, director):
    r = ask(director)
    assert r.status_code == 200
    record = audit.find_query(r.json()["query_id"])
    assert record["username"] == "admin" and record["sql"] and record["row_count"] == len(r.json()["rows"])


@requires_db
def test_director_downloads_pdf(no_llm, director):
    query_id = ask(director).json()["query_id"]
    r = client.post(f"/api/reports/{query_id}", headers=director)
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert "attachment" in r.headers["content-disposition"] and query_id in r.headers["content-disposition"]
    assert r.content.startswith(b"%PDF")
    assert audit.recent_events("admin", 1)[0]["event"] == "report"      # la descarga también queda auditada


@requires_db
def test_service_head_cannot_download_report(no_llm, director):
    head = create_user(director, "jefe.uci", "service_head", "UCI")
    query_id = ask(head).json()["query_id"]
    assert client.post(f"/api/reports/{query_id}", headers=head).status_code == 403


@requires_db
def test_director_cannot_download_other_users_query(no_llm, director):
    other = create_user(director, "gerente2", "director")
    query_id = ask(other).json()["query_id"]
    assert client.post(f"/api/reports/{query_id}", headers=director).status_code == 404


def test_rejected_query_is_audited_without_report(director):
    r = ask(director, "Dame la cédula de los pacientes")
    assert r.status_code == 400
    last = audit.recent_events("admin", 1)[0]
    assert last["status"] == "error" and "privacidad" in last["error"]
    assert client.post(f"/api/reports/{last['id']}", headers=director).status_code == 400


def test_unknown_query_id_returns_404(director):
    assert client.post("/api/reports/noexiste", headers=director).status_code == 404


def test_audit_chain_detects_tampering(tmp_path):
    user = {"username": "admin", "name": "Dirección", "role": "director"}
    for q in ("uno", "dos", "tres"):
        audit.log_query(user, q, result={"source": "rules", "answer": "x", "sql": "SELECT 1",
                                         "columns": ["n"], "rows": [[1]]})
    assert audit.verify_chain() == (True, 3)
    path = tmp_path / "audit.jsonl"
    lines = path.read_text(encoding="utf-8").splitlines()
    tampered = json.loads(lines[1])
    tampered["question"] = "editada"
    lines[1] = json.dumps(tampered, ensure_ascii=False)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    assert audit.verify_chain()[0] is False
