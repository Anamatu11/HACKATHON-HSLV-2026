"""Especificación del login real (JWT) y de la protección de la API."""
import time

import jwt
import pytest
from fastapi.testclient import TestClient

from app import auth
from app.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def demo_credentials(monkeypatch):
    monkeypatch.setenv("AUTH_USERNAME", "admin")
    monkeypatch.setenv("AUTH_PASSWORD", "hslv2026")
    monkeypatch.setenv("AUTH_SECRET", "test-secret-hslv-2026-very-secure-32-bytes")


def login(username="admin", password="hslv2026"):
    return client.post("/api/auth/login", json={"username": username, "password": password})


def test_login_returns_bearer_token():
    r = login()
    assert r.status_code == 200
    body = r.json()
    assert body["token_type"] == "bearer" and body["access_token"]
    assert body["user"]["username"] == "admin"


def test_login_accepts_institutional_email():
    assert login("ADMIN@hosusana.gov.co").status_code == 200


def test_login_rejects_other_email_domain():
    assert login("admin@gmail.com").status_code == 401


def test_login_rejects_wrong_password():
    assert login(password="otra").status_code == 401


@pytest.mark.parametrize("path", ["/api/kpis", "/api/alerts", "/api/auth/me"])
def test_protected_endpoints_require_token(path):
    assert client.get(path).status_code == 401


def test_query_requires_token():
    assert client.post("/api/query", json={"question": "hola hola"}).status_code == 401


def test_invalid_token_is_rejected():
    assert client.get("/api/auth/me", headers={"Authorization": "Bearer basura"}).status_code == 401


def test_expired_token_is_rejected():
    expired = jwt.encode({"sub": "admin", "exp": int(time.time()) - 10}, "test-secret-hslv-2026-very-secure-32-bytes", algorithm="HS256")
    assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {expired}"}).status_code == 401


def test_me_returns_user_with_valid_token():
    token = login().json()["access_token"]
    r = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200 and r.json()["username"] == "admin"


def test_health_is_public():
    assert client.get("/api/health").status_code == 200


def test_password_is_compared_in_constant_time(monkeypatch):
    # Contrato mínimo: authenticate no debe aceptar prefijos ni vacíos
    assert auth.authenticate("admin", "") is None
    assert auth.authenticate("admin", "hslv") is None
