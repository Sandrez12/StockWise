from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Response, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.deps import AdminUser, DbSession, StaffUser
from app.models import Category, Product, UserRole
from app.schemas import (
    CategoryCreate,
    CategoryRead,
    CategoryUpdate,
    ErrorResponse,
    Page,
)

router = APIRouter(
    prefix="/categories",
    tags=["Categorías"],
    responses={
        401: {"model": ErrorResponse, "description": "Token ausente, inválido o expirado"},
        403: {"model": ErrorResponse, "description": "Permisos insuficientes"},
    },
)

NOT_FOUND = {404: {"model": ErrorResponse, "description": "Categoría no encontrada"}}
CONFLICT = {409: {"model": ErrorResponse, "description": "Conflicto con otra categoría o con productos"}}


def _name_taken(db: DbSession, name: str, exclude_id: int | None = None) -> bool:
    query = select(Category.id).where(func.lower(Category.name) == name.lower())
    if exclude_id is not None:
        query = query.where(Category.id != exclude_id)
    return db.scalar(query) is not None


def _has_active_products(db: DbSession, category_id: int) -> bool:
    return (
        db.scalar(
            select(Product.id)
            .where(Product.category_id == category_id, Product.is_active.is_(True))
            .limit(1)
        )
        is not None
    )


def _get_visible(db: DbSession, category_id: int, user) -> Category:
    category = db.get(Category, category_id)
    if category is None or (not category.is_active and user.role != UserRole.ADMIN):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Categoría no encontrada")
    return category


@router.post(
    "",
    response_model=CategoryRead,
    status_code=status.HTTP_201_CREATED,
    summary="Crear categoría",
    description="Solo administradores. El nombre es único sin distinguir mayúsculas.",
    responses=CONFLICT,
)
def create_category(data: CategoryCreate, db: DbSession, _admin: AdminUser) -> Category:
    if _name_taken(db, data.name):
        raise HTTPException(status.HTTP_409_CONFLICT, "Ya existe una categoría con ese nombre")
    category = Category(name=data.name, description=data.description)
    db.add(category)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Ya existe una categoría con ese nombre"
        ) from None
    db.refresh(category)
    return category


@router.get(
    "",
    response_model=Page[CategoryRead],
    summary="Listar categorías",
    description=(
        "Administradores y operadores. Por defecto solo las activas; "
        "`include_inactive=true` es exclusivo de administradores."
    ),
)
def list_categories(
    db: DbSession,
    user: StaffUser,
    q: Annotated[str | None, Query(max_length=100, description="Búsqueda por nombre")] = None,
    include_inactive: bool = False,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Page[CategoryRead]:
    if include_inactive and user.role != UserRole.ADMIN:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Permisos insuficientes")
    filters = []
    if not include_inactive:
        filters.append(Category.is_active.is_(True))
    if q:
        escaped = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        filters.append(Category.name.ilike(f"%{escaped}%", escape="\\"))
    total = db.scalar(select(func.count()).select_from(Category).where(*filters)) or 0
    rows = db.scalars(
        select(Category).where(*filters).order_by(Category.name, Category.id).limit(limit).offset(offset)
    )
    return Page(items=list(rows), total=total, limit=limit, offset=offset)


@router.get(
    "/{category_id}",
    response_model=CategoryRead,
    summary="Obtener categoría",
    responses=NOT_FOUND,
)
def get_category(category_id: int, db: DbSession, user: StaffUser) -> Category:
    return _get_visible(db, category_id, user)


@router.patch(
    "/{category_id}",
    response_model=CategoryRead,
    summary="Actualizar categoría",
    description=(
        "Solo administradores. `is_active=false` equivale a borrar; no se permite si la "
        "categoría tiene productos activos."
    ),
    responses={**NOT_FOUND, **CONFLICT},
)
def update_category(
    category_id: int, data: CategoryUpdate, db: DbSession, _admin: AdminUser
) -> Category:
    category = db.get(Category, category_id)
    if category is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Categoría no encontrada")
    changes = data.model_dump(exclude_unset=True)
    if changes.get("name") is None:
        changes.pop("name", None)
    if changes.get("is_active") is None:
        changes.pop("is_active", None)
    if "name" in changes and _name_taken(db, changes["name"], exclude_id=category.id):
        raise HTTPException(status.HTTP_409_CONFLICT, "Ya existe una categoría con ese nombre")
    if changes.get("is_active") is False and _has_active_products(db, category.id):
        raise HTTPException(
            status.HTTP_409_CONFLICT, "La categoría tiene productos activos"
        )
    for field, value in changes.items():
        setattr(category, field, value)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Ya existe una categoría con ese nombre"
        ) from None
    db.refresh(category)
    return category


@router.delete(
    "/{category_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Borrar (desactivar) categoría",
    description="Borrado lógico: pone `is_active=false`. Idempotente. Falla si tiene productos activos.",
    responses={**NOT_FOUND, **CONFLICT},
)
def delete_category(category_id: int, db: DbSession, _admin: AdminUser) -> Response:
    category = db.get(Category, category_id)
    if category is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Categoría no encontrada")
    if category.is_active:
        if _has_active_products(db, category.id):
            raise HTTPException(status.HTTP_409_CONFLICT, "La categoría tiene productos activos")
        category.is_active = False
        db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
