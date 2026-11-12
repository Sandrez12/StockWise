"""Dependencias de autenticación y autorización."""

from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User, UserRole
from app.security import decode_access_token

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")

DbSession = Annotated[Session, Depends(get_db)]


def _credentials_error() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="No se pudieron validar las credenciales",
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)], db: DbSession
) -> User:
    """Usuario del token. Rechaza tokens inválidos/expirados y usuarios inactivos."""
    try:
        user_id = int(decode_access_token(token)["sub"])
    except (jwt.PyJWTError, ValueError):
        raise _credentials_error() from None
    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise _credentials_error()
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_role(*roles: UserRole):
    """Dependencia que exige que el usuario tenga alguno de los roles dados."""
    allowed = frozenset(roles)

    def checker(user: CurrentUser) -> User:
        if user.role not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Permisos insuficientes",
            )
        return user

    return checker


AdminUser = Annotated[User, Depends(require_role(UserRole.ADMIN))]
