"""Especificación del módulo de permisos por rol (Dirección / Jefe de servicio)."""
import pytest
from fastapi.testclient import TestClient

from app import permissions
from app.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def isolated_access(monkeypatch, tmp_path):
    monkeypatch.setenv("AUTH_USERNAME", "admin")
    monkeypatch.setenv("AUTH_PASSWORD", "hslv2026")
    monkeypatch.setenv("AUTH_SECRET", "test-secret-hslv-2026-very-secure-32-bytes")
    monkeypatch.setenv("ACCESS_PATH", str(tmp_path / "access.json"))


def headers_for(username, password):
    r = client.post("/api/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture
def director():
    return headers_for("admin", "hslv2026")


def create_head(director, username="jefe.uci", service="UCI"):
    r = client.post("/api/users", headers=director, json={
        "username": username, "name": "Jefe UCI", "role": "service_head", "service": service,
        "password": "clave-segura-1"})
    assert r.status_code == 201, r.text
    return headers_for(username, "clave-segura-1")


def test_env_user_is_director_with_all_modules(director):
    me = client.get("/api/auth/me", headers=director).json()
    assert me["role"] == "director" and me["role_label"] == "Gerencia / Dirección"
    assert me["permissions"] == permissions.MODULE_KEYS


def test_login_response_includes_permissions():
    user = client.post("/api/auth/login", json={"username": "admin", "password": "hslv2026"}).json()["user"]
    assert "permissions" in user


def test_director_creates_service_head_who_can_log_in(director):
    head = create_head(director)
    me = client.get("/api/auth/me", headers=head).json()
    assert me["role"] == "service_head" and me["service"] == "UCI"
    assert "permissions" not in me["permissions"]


def test_password_is_stored_hashed(director, tmp_path):
    create_head(director)
    raw = (tmp_path / "access.json").read_text(encoding="utf-8")
    assert "clave-segura-1" not in raw and "pbkdf2_sha256$" in raw


def test_service_head_cannot_manage_permissions(director):
    head = create_head(director)
    assert client.get("/api/permissions", headers=head).status_code == 403
    assert client.get("/api/users", headers=head).status_code == 403
    assert client.post("/api/users", headers=head, json={
        "username": "otro", "name": "Otro", "role": "director", "password": "12345678"}).status_code == 403


def test_service_head_requires_service(director):
    r = client.post("/api/users", headers=director, json={
        "username": "sin.servicio", "name": "Usuario X", "role": "service_head", "password": "clave-segura-1"})
    assert r.status_code == 400


def test_duplicate_or_env_username_is_rejected(director):
    create_head(director)
    for username in ("jefe.uci", "admin"):
        r = client.post("/api/users", headers=director, json={
            "username": username, "name": "Usuario X", "role": "director", "password": "clave-segura-1"})
        assert r.status_code == 409


def test_revoking_module_blocks_endpoint(director):
    head = create_head(director)
    r = client.put("/api/permissions", headers=director, json={"matrix": {"service_head": {"alerts": False}}})
    assert r.status_code == 200 and r.json()["matrix"]["service_head"]["alerts"] is False
    assert client.get("/api/alerts", headers=head).status_code == 403
    assert "alerts" not in client.get("/api/auth/me", headers=head).json()["permissions"]


def test_director_cannot_lock_itself_out(director):
    client.put("/api/permissions", headers=director, json={"matrix": {"director": {"permissions": False}}})
    assert client.get("/api/permissions", headers=director).status_code == 200


def test_unknown_module_is_rejected(director):
    r = client.put("/api/permissions", headers=director, json={"matrix": {"service_head": {"root": True}}})
    assert r.status_code == 400


def test_deactivated_user_loses_access_immediately(director):
    head = create_head(director)
    assert client.patch("/api/users/jefe.uci", headers=director, json={"active": False}).status_code == 200
    assert client.get("/api/auth/me", headers=head).status_code == 401
    r = client.post("/api/auth/login", json={"username": "jefe.uci", "password": "clave-segura-1"})
    assert r.status_code == 401


def test_role_change_applies_without_new_login(director):
    head = create_head(director)
    client.patch("/api/users/jefe.uci", headers=director, json={"role": "director"})
    assert client.get("/api/permissions", headers=head).status_code == 200


def test_delete_user(director):
    create_head(director)
    assert client.delete("/api/users/jefe.uci", headers=director).status_code == 204
    names = [u["username"] for u in client.get("/api/users", headers=director).json()]
    assert names == ["admin"]


def test_verify_password_rejects_wrong_or_malformed():
    stored = permissions.hash_password("correcta-123")
    assert permissions.verify_password("correcta-123", stored)
    assert not permissions.verify_password("otra", stored)
    assert not permissions.verify_password("x", "basura")
