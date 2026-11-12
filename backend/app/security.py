"""Hash de contraseñas (argon2id vía pwdlib) y tokens JWT de acceso (PyJWT)."""

from datetime import datetime, timedelta, timezone

import jwt
from pwdlib import PasswordHash
from pwdlib.exceptions import UnknownHashError

from app.config import get_settings

ALGORITHM = "HS256"

_password_hash = PasswordHash.recommended()

# Hash de una contraseña descartable. El login lo verifica cuando el correo no
# existe, para que la respuesta tarde lo mismo y no revele qué correos existen.
DUMMY_HASH = _password_hash.hash("contraseña-descartable-para-igualar-tiempos")


def hash_password(password: str) -> str:
    return _password_hash.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    try:
        return _password_hash.verify(password, hashed)
    except UnknownHashError:
        return False


def create_access_token(subject: str, expires_delta: timedelta | None = None) -> str:
    settings = get_settings()
    now = datetime.now(timezone.utc)
    delta = expires_delta or timedelta(minutes=settings.access_token_expire_minutes)
    payload = {"sub": subject, "iat": now, "exp": now + delta}
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)


def decode_access_token(token: str) -> dict:
    """Devuelve las claims o lanza jwt.PyJWTError (firma, expiración, formato)."""
    return jwt.decode(
        token,
        get_settings().secret_key,
        algorithms=[ALGORITHM],
        options={"require": ["exp", "sub"]},
    )
