from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select

from app.config import get_settings
from app.deps import CurrentUser, DbSession
from app.models import User
from app.schemas import Token, UserRead
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
    responses={401: {"description": "Credenciales incorrectas"}},
)
def login(form: Annotated[OAuth2PasswordRequestForm, Depends()], db: DbSession) -> Token:
    email = form.username.strip().lower()
    user = db.scalar(select(User).where(User.email == email))
    # Se verifica siempre un hash (el real o uno descartable) para igualar tiempos.
    password_ok = verify_password(form.password, user.hashed_password if user else DUMMY_HASH)
    if user is None or not password_ok or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Correo o contraseña incorrectos",
            headers={"WWW-Authenticate": "Bearer"},
        )
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
