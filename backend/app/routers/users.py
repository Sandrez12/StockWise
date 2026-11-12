from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.deps import AdminUser, DbSession
from app.models import User
from app.schemas import UserActiveUpdate, UserCreate, UserRead, UserRoleUpdate
from app.security import hash_password

router = APIRouter(
    prefix="/users",
    tags=["Usuarios"],
    responses={
        401: {"description": "Token ausente, inválido o expirado"},
        403: {"description": "Solo administradores"},
    },
)


def _get_or_404(db: DbSession, user_id: int) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Usuario no encontrado")
    return user


@router.post(
    "",
    response_model=UserRead,
    status_code=status.HTTP_201_CREATED,
    summary="Crear usuario",
    description="Solo administradores. No existe registro público.",
    responses={409: {"description": "El correo ya está registrado"}},
)
def create_user(data: UserCreate, db: DbSession, _admin: AdminUser) -> User:
    if db.scalar(select(User.id).where(User.email == data.email)) is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "El correo ya está registrado")
    user = User(
        email=data.email,
        full_name=data.full_name,
        hashed_password=hash_password(data.password),
        role=data.role,
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError:  # carrera con otra petición que creó el mismo correo
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "El correo ya está registrado") from None
    db.refresh(user)
    return user


@router.get("", response_model=list[UserRead], summary="Listar usuarios")
def list_users(
    db: DbSession,
    _admin: AdminUser,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[User]:
    return list(db.scalars(select(User).order_by(User.id).limit(limit).offset(offset)))


@router.patch(
    "/{user_id}/role",
    response_model=UserRead,
    summary="Cambiar el rol de un usuario",
    description="Un administrador no puede cambiar su propio rol (evita quedarse sin administradores).",
    responses={404: {"description": "Usuario no encontrado"}, 409: {"description": "Cambio sobre uno mismo"}},
)
def update_role(user_id: int, data: UserRoleUpdate, db: DbSession, admin: AdminUser) -> User:
    user = _get_or_404(db, user_id)
    if user.id == admin.id:
        raise HTTPException(status.HTTP_409_CONFLICT, "No puedes cambiar tu propio rol")
    user.role = data.role
    db.commit()
    db.refresh(user)
    return user


@router.patch(
    "/{user_id}/active",
    response_model=UserRead,
    summary="Activar o desactivar un usuario",
    description="Un administrador no puede desactivarse a sí mismo. Un usuario inactivo no puede iniciar sesión ni usar tokens ya emitidos.",
    responses={404: {"description": "Usuario no encontrado"}, 409: {"description": "Cambio sobre uno mismo"}},
)
def update_active(user_id: int, data: UserActiveUpdate, db: DbSession, admin: AdminUser) -> User:
    user = _get_or_404(db, user_id)
    if user.id == admin.id:
        raise HTTPException(status.HTTP_409_CONFLICT, "No puedes cambiar tu propio estado")
    user.is_active = data.is_active
    db.commit()
    db.refresh(user)
    return user
