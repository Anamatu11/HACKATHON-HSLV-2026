"""
Permisos por rol: Gerencia/Dirección y Jefes de servicio.

Responsable: Rol A.

- Dos roles: `director` (Gerencia / Dirección) y `service_head` (Jefe de servicio, asociado a un servicio).
- Matriz rol × módulo editable por quien tenga el módulo "permissions" (por defecto solo Dirección).
  Dirección nunca pierde "permissions" para que nadie quede bloqueado fuera del panel.
- Usuarios adicionales creados desde el panel, con contraseña en hash PBKDF2-SHA256 (stdlib, sin dependencias).
  El usuario del .env (AUTH_USERNAME) es siempre Dirección y no se puede editar desde aquí.
- Todo se guarda en `data/access.json` (ACCESS_PATH), que está en .gitignore junto con data/.

Rutas: GET/PUT /api/permissions, GET/POST /api/users, PATCH/DELETE /api/users/{username}.
Las demás rutas usan `require_permission("<módulo>")`.
"""
import hashlib
import hmac
import json
import os
import re
import secrets
import threading
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app import auth, db

ROLES = {"director": "Gerencia / Dirección", "service_head": "Jefe de servicio"}

# Orden = orden de las pestañas del panel
MODULES = [
    {"key": "dashboard", "label": "Dashboard", "detail": "Tarjetas KPI y gráficos generales"},
    {"key": "occupancy", "label": "Ocupación", "detail": "Ocupación por servicio, subservicio y especialidad"},
    {"key": "assistant", "label": "Asistente IA", "detail": "Preguntas en lenguaje natural (NL2SQL)"},
    {"key": "alerts", "label": "Alertas", "detail": "Alertas y recomendaciones automáticas"},
    {"key": "medications", "label": "Medicamentos", "detail": "Inventario y rotación de medicamentos"},
    {"key": "permissions", "label": "Permisos", "detail": "Administrar usuarios y permisos por rol"},
]
MODULE_KEYS = [m["key"] for m in MODULES]

DEFAULT_MATRIX = {
    "director": {m: True for m in MODULE_KEYS},
    "service_head": {m: m != "permissions" for m in MODULE_KEYS},
}
LOCKED = {("director", "permissions")}      # no editable: evita que Dirección se bloquee a sí misma

USERNAME_RE = re.compile(r"^[a-z0-9._-]{3,40}$")
PBKDF2_ITERATIONS = 200_000
_lock = threading.Lock()

router = APIRouter(prefix="/api", tags=["permissions"])


# --- Almacenamiento ------------------------------------------------------------------

def _path() -> Path:
    return Path(os.getenv("ACCESS_PATH", "data/access.json"))


def _load() -> dict:
    try:
        data = json.loads(_path().read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        data = {}
    matrix = {role: {**DEFAULT_MATRIX[role], **data.get("matrix", {}).get(role, {})} for role in ROLES}
    for role, module in LOCKED:
        matrix[role][module] = True
    return {"matrix": matrix, "users": data.get("users", {})}


def _save(data: dict) -> None:
    path = _path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)                       # escritura atómica


# --- Contraseñas ---------------------------------------------------------------------

def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), PBKDF2_ITERATIONS).hex()
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${salt}${digest}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, iterations, salt, digest = stored.split("$")
        candidate = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), int(iterations)).hex()
    except ValueError:
        return False
    return hmac.compare_digest(candidate, digest)


# --- Consultas usadas por auth.py ------------------------------------------------------

def _public(username: str, u: dict) -> dict:
    return {"username": username, "name": u["name"], "role": u["role"],
            "service": u.get("service"), "active": u.get("active", True)}


def find_user(username: str) -> dict | None:
    """Usuario creado desde el panel (sin hash), o None."""
    u = _load()["users"].get(username)
    return _public(username, u) if u else None


def authenticate_stored(username: str, password: str) -> dict | None:
    u = _load()["users"].get(username)
    if not u or not u.get("active", True) or not verify_password(password, u["password_hash"]):
        return None
    return _public(username, u)


def permissions_for(role: str) -> list[str]:
    row = _load()["matrix"].get(role, {})
    return [m for m in MODULE_KEYS if row.get(m)]


def describe(user: dict) -> dict:
    """Usuario + etiqueta del rol + módulos permitidos (lo que necesita el frontend)."""
    return {**user, "role_label": ROLES.get(user.get("role"), user.get("role")),
            "permissions": permissions_for(user.get("role", ""))}


def require_permission(*modules: str):
    """Dependencia: exige sesión y al menos uno de los módulos indicados."""
    def dependency(user: dict = Depends(auth.require_user)) -> dict:
        allowed = permissions_for(user["role"])
        if not any(m in allowed for m in modules):
            raise HTTPException(status_code=403, detail="Su rol no tiene permiso para este módulo.")
        return user
    return dependency


# --- API -----------------------------------------------------------------------------

class MatrixUpdate(BaseModel):
    matrix: dict[str, dict[str, bool]]


class UserCreate(BaseModel):
    username: str = Field(..., min_length=3, max_length=40)
    name: str = Field(..., min_length=2, max_length=80)
    role: str
    service: str | None = Field(None, max_length=60)
    password: str = Field(..., min_length=8, max_length=120)


class UserUpdate(BaseModel):
    name: str | None = Field(None, min_length=2, max_length=80)
    role: str | None = None
    service: str | None = Field(None, max_length=60)
    active: bool | None = None
    password: str | None = Field(None, min_length=8, max_length=120)


def _check_role(role: str, service: str | None) -> None:
    if role not in ROLES:
        raise HTTPException(status_code=400, detail="Rol no válido.")
    if role == "service_head" and not (service or "").strip():
        raise HTTPException(status_code=400, detail="Un jefe de servicio debe tener un servicio asignado.")


def _services() -> list[str]:
    """Servicios con camas (opciones para asignar a un jefe de servicio)."""
    try:
        _, rows = db.run_query("SELECT DISTINCT service FROM bed_capacity ORDER BY service")
        return [r[0] for r in rows]
    except Exception:          # sin BD el módulo de permisos sigue funcionando
        return []


@router.get("/permissions")
def get_permissions(_user: dict = Depends(require_permission("permissions"))) -> dict:
    return {"roles": [{"key": k, "label": v} for k, v in ROLES.items()], "modules": MODULES,
            "matrix": _load()["matrix"], "locked": [list(x) for x in LOCKED], "services": _services()}


@router.put("/permissions")
def update_permissions(req: MatrixUpdate, _user: dict = Depends(require_permission("permissions"))) -> dict:
    with _lock:
        data = _load()
        for role, row in req.matrix.items():
            if role not in ROLES:
                raise HTTPException(status_code=400, detail=f"Rol no válido: {role}")
            for module, allowed in row.items():
                if module not in MODULE_KEYS:
                    raise HTTPException(status_code=400, detail=f"Módulo no válido: {module}")
                if (role, module) not in LOCKED:
                    data["matrix"][role][module] = bool(allowed)
        _save(data)
    return get_permissions(_user)


@router.get("/users")
def list_users(_user: dict = Depends(require_permission("permissions"))) -> list[dict]:
    admin = os.getenv("AUTH_USERNAME", "admin").lower()
    env_user = {"username": admin, "name": auth.DIRECTOR_NAME, "role": "director", "service": None,
                "active": True, "built_in": True}
    stored = [{**_public(k, u), "built_in": False} for k, u in sorted(_load()["users"].items())]
    return [env_user, *stored]


@router.post("/users", status_code=201)
def create_user(req: UserCreate, _user: dict = Depends(require_permission("permissions"))) -> dict:
    username = req.username.strip().lower()
    if not USERNAME_RE.match(username):
        raise HTTPException(status_code=400, detail="Usuario: 3-40 caracteres (letras, números, punto, guion).")
    _check_role(req.role, req.service)
    with _lock:
        data = _load()
        if username == os.getenv("AUTH_USERNAME", "admin").lower() or username in data["users"]:
            raise HTTPException(status_code=409, detail="Ese usuario ya existe.")
        data["users"][username] = {
            "name": req.name.strip(), "role": req.role, "active": True,
            "service": req.service.strip() if req.role == "service_head" and req.service else None,
            "password_hash": hash_password(req.password),
        }
        _save(data)
        return _public(username, data["users"][username])


@router.patch("/users/{username}")
def update_user(username: str, req: UserUpdate, _user: dict = Depends(require_permission("permissions"))) -> dict:
    with _lock:
        data = _load()
        u = data["users"].get(username)
        if u is None:
            raise HTTPException(status_code=404, detail="Usuario no encontrado (el usuario del .env no se edita aquí).")
        role = req.role or u["role"]
        service = req.service if req.service is not None else u.get("service")
        _check_role(role, service)
        if req.name is not None:
            u["name"] = req.name.strip()
        u["role"] = role
        u["service"] = service.strip() if role == "service_head" and service else None
        if req.active is not None:
            u["active"] = req.active
        if req.password:
            u["password_hash"] = hash_password(req.password)
        _save(data)
        return _public(username, u)


@router.delete("/users/{username}", status_code=204)
def delete_user(username: str, _user: dict = Depends(require_permission("permissions"))) -> None:
    with _lock:
        data = _load()
        if data["users"].pop(username, None) is None:
            raise HTTPException(status_code=404, detail="Usuario no encontrado.")
        _save(data)
