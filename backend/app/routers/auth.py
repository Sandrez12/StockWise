from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select

from app.config import get_settings
from app.deps import CurrentUser, DbSession
from app.models import User
from app.ratelimit import login_limiter
from app.schemas import ErrorResponse, Token, UserRead
from app.security import DUMMY_HASH, create_access_token, verify_password

router = APIRouter(prefix="/auth", tags=["Autenticación"])


@router.post(
    "/login",
    response_model=Token,
    summary="Iniciar sesión",
    description=(
        "Formulario OAuth2 (`username` = correo, `password`). Devuelve un token de "
        "acceso JWT. El mensaje de error es el mismo si el correo no existe, la "
        "contraseña es incorrecta o el usuario está inactivo."
    ),
    responses={
        401: {"model": ErrorResponse, "description": "Credenciales incorrectas"},
        429: {
            "model": ErrorResponse,
            "description": (
                "5 intentos fallidos en 15 minutos para esa IP y correo. "
                "La cabecera `Retry-After` indica los segundos de espera."
            ),
        },
    },
)
def login(
    form: Annotated[OAuth2PasswordRequestForm, Depends()], db: DbSession, request: Request
) -> Token:
    email = form.username.strip().lower()
    ip = request.client.host if request.client else "desconocida"
    # El bloqueo se aplica antes de verificar la contraseña y cuenta igual si el
    # correo existe o no, para no revelarlo.
    wait = login_limiter.retry_after(ip, email)
    if wait:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Demasiados intentos fallidos. Inténtalo de nuevo más tarde",
            headers={"Retry-After": str(wait)},
        )
    user = db.scalar(select(User).where(User.email == email))
    # Se verifica siempre un hash (el real o uno descartable) para igualar tiempos.
    password_ok = verify_password(form.password, user.hashed_password if user else DUMMY_HASH)
    if user is None or not password_ok or not user.is_active:
        login_limiter.register_failure(ip, email)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Correo o contraseña incorrectos",
            headers={"WWW-Authenticate": "Bearer"},
        )
    login_limiter.reset(ip, email)
    minutes = get_settings().access_token_expire_minutes
    return Token(access_token=create_access_token(str(user.id)), expires_in=minutes * 60)


@router.get(
    "/me",
    response_model=UserRead,
    summary="Usuario autenticado",
    responses={401: {"description": "Token ausente, inválido o expirado"}},
)
def me(user: CurrentUser) -> User:
    return user
