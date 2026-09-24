"""
Autenticación: login con usuario/contraseña del .env y token JWT (HS256).

Responsable: Rol A.

Variables (.env):
    AUTH_USERNAME   usuario (default: admin)
    AUTH_PASSWORD   contraseña (default de DEMO: hslv2026; cambiarla fuera de la demo)
    AUTH_SECRET     clave para firmar tokens; si falta se genera una al arrancar
                    (los tokens dejan de valer al reiniciar el servidor)

El usuario puede escribir "admin" o su correo institucional "admin@hosusana.gov.co".
El usuario del .env es siempre Gerencia / Dirección. Los demás usuarios (p. ej. jefes de servicio) se crean
desde la pestaña Permisos y viven en data/access.json (ver app/permissions.py).
Rutas: POST /api/auth/login, GET /api/auth/me. Las demás rutas /api/* usan `require_user`
o `permissions.require_permission(<módulo>)`.
"""
import hmac
import logging
import os
import secrets
import time

import jwt
from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

ALGORITHM = "HS256"
TOKEN_TTL_SECONDS = 8 * 60 * 60          # una jornada
INSTITUTIONAL_DOMAIN = "hosusana.gov.co"
DEMO_PASSWORD = "hslv2026"
DIRECTOR_NAME = "Dirección HSLV"
_GENERATED_SECRET = secrets.token_urlsafe(32)

router = APIRouter(prefix="/api/auth", tags=["auth"])
bearer = HTTPBearer(auto_error=False)


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=120)
    password: str = Field(..., min_length=1, max_length=120)


def _secret() -> str:
    return os.getenv("AUTH_SECRET") or _GENERATED_SECRET


def _normalize_username(identifier: str) -> str | None:
    """'admin' o 'admin@hosusana.gov.co' -> 'admin'. Otro dominio -> None."""
    value = identifier.strip().lower()
    if "@" in value:
        user, _, domain = value.partition("@")
        return user if domain == INSTITUTIONAL_DOMAIN else None
    return value


def authenticate(identifier: str, password: str) -> dict | None:
    """Devuelve el usuario si las credenciales son válidas; si no, None."""
    expected_user = os.getenv("AUTH_USERNAME", "admin").lower()
    expected_password = os.getenv("AUTH_PASSWORD") or DEMO_PASSWORD
    username = _normalize_username(identifier)
    # compare_digest evita filtrar información por el tiempo de respuesta
    user_ok = hmac.compare_digest((username or "").encode(), expected_user.encode())
    password_ok = hmac.compare_digest(password.encode(), expected_password.encode())
    if user_ok and password_ok:
        return {"username": expected_user, "name": DIRECTOR_NAME, "role": "director", "service": None}
    if username is None or username == expected_user:
        return None
    from app import permissions   # import diferido: permissions depende de este módulo
    return permissions.authenticate_stored(username, password)


def create_token(user: dict) -> str:
    now = int(time.time())
    claims = {"sub": user["username"], "name": user["name"], "role": user["role"],
              "service": user.get("service"), "iat": now, "exp": now + TOKEN_TTL_SECONDS}
    return jwt.encode(claims, _secret(), algorithm=ALGORITHM)


def require_user(credentials: HTTPAuthorizationCredentials | None = Depends(bearer)) -> dict:
    """Dependencia de FastAPI: exige un Bearer token válido y vigente."""
    if credentials is None:
        raise HTTPException(status_code=401, detail="Inicie sesión para continuar.")
    try:
        claims = jwt.decode(credentials.credentials, _secret(), algorithms=[ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="La sesión expiró. Inicie sesión de nuevo.")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Sesión inválida. Inicie sesión de nuevo.")
    username = claims["sub"]
    if username == os.getenv("AUTH_USERNAME", "admin").lower():
        return {"username": username, "name": claims.get("name", ""), "role": claims.get("role", ""),
                "service": claims.get("service")}
    # Usuario creado desde el panel: rol y estado se leen en cada petición, así desactivarlo o
    # cambiarle el rol aplica de inmediato sin esperar a que venza el token.
    from app import permissions
    user = permissions.find_user(username)
    if user is None or not user["active"]:
        raise HTTPException(status_code=401, detail="Usuario desactivado. Contacte a Dirección.")
    return {k: user[k] for k in ("username", "name", "role", "service")}


@router.post("/login")
def login(req: LoginRequest) -> dict:
    user = authenticate(req.username, req.password)
    if user is None:
        logger.warning("Login fallido para '%s'", req.username)
        raise HTTPException(status_code=401, detail="Usuario o contraseña incorrectos.")
    from app import permissions
    return {"access_token": create_token(user), "token_type": "bearer",
            "expires_in": TOKEN_TTL_SECONDS, "user": permissions.describe(user)}


@router.get("/me")
def me(user: dict = Depends(require_user)) -> dict:
    from app import permissions
    return permissions.describe(user)
