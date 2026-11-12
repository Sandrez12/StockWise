from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import func, select

from app.deps import AdminUser, DbSession, StaffUser
from app.models import MovementType, StockMovement, UserRole
from app.schemas import (
    ErrorResponse,
    MovementCreate,
    MovementRead,
    Page,
    StockCount,
    StockCountResult,
)
from app.services import stock as stock_service

router = APIRouter(
    tags=["Movimientos de stock"],
    responses={
        401: {"model": ErrorResponse, "description": "Token ausente, inválido o expirado"},
        403: {"model": ErrorResponse, "description": "Permisos insuficientes"},
    },
)

PRODUCT_ERRORS = {
    404: {"model": ErrorResponse, "description": "Producto no encontrado"},
    409: {
        "model": ErrorResponse,
        "description": "`insufficient_stock` (el stock quedaría negativo) o `inactive_product`",
    },
}


def _as_utc(value: datetime | None) -> datetime | None:
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


@router.post(
    "/stock-movements",
    response_model=MovementRead,
    status_code=status.HTTP_201_CREATED,
    summary="Registrar un movimiento de stock",
    description=(
        "`entrada` y `salida` (cantidad positiva): admin y operator. `ajuste` (cantidad con "
        "signo): solo admin. El usuario del movimiento es el del token. Todo ocurre en una "
        "transacción con el producto bloqueado (`SELECT ... FOR UPDATE`): una salida que dejaría "
        "el stock negativo devuelve 409 `insufficient_stock` y no cambia nada."
    ),
    responses=PRODUCT_ERRORS,
)
def create_movement(data: MovementCreate, db: DbSession, user: StaffUser) -> StockMovement:
    if data.type == MovementType.AJUSTE and user.role != UserRole.ADMIN:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Permisos insuficientes")
    return stock_service.register_movement(
        db, user, data.product_id, data.type, data.quantity, data.reason
    )


@router.get(
    "/stock-movements",
    response_model=Page[MovementRead],
    summary="Listar movimientos de stock",
    description=(
        "Admin y operator, solo lectura, del más reciente al más antiguo. Los movimientos son "
        "inmutables: no existen PATCH ni DELETE. Las fechas son ISO 8601; sin zona se asumen UTC; "
        "`date_from` y `date_to` son inclusivos."
    ),
)
def list_movements(
    db: DbSession,
    _user: StaffUser,
    product_id: Annotated[int | None, Query(description="Filtrar por producto")] = None,
    type: Annotated[MovementType | None, Query(description="Filtrar por tipo")] = None,
    user_id: Annotated[int | None, Query(description="Filtrar por usuario")] = None,
    date_from: Annotated[datetime | None, Query(description="Desde (inclusive)")] = None,
    date_to: Annotated[datetime | None, Query(description="Hasta (inclusive)")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Page[MovementRead]:
    date_from, date_to = _as_utc(date_from), _as_utc(date_to)
    if date_from and date_to and date_from > date_to:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "date_from no puede ser posterior a date_to")
    filters = []
    if product_id is not None:
        filters.append(StockMovement.product_id == product_id)
    if type is not None:
        filters.append(StockMovement.type == type)
    if user_id is not None:
        filters.append(StockMovement.user_id == user_id)
    if date_from is not None:
        filters.append(StockMovement.created_at >= date_from)
    if date_to is not None:
        filters.append(StockMovement.created_at <= date_to)
    total = db.scalar(select(func.count()).select_from(StockMovement).where(*filters)) or 0
    rows = db.scalars(
        select(StockMovement)
        .where(*filters)
        .order_by(StockMovement.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return Page(items=list(rows), total=total, limit=limit, offset=offset)


@router.post(
    "/products/{product_id}/stock-count",
    response_model=StockCountResult,
    summary="Conteo físico de un producto",
    description=(
        "Solo admin. Recibe el valor contado; bajo bloqueo del producto calcula la diferencia "
        "con el stock registrado y la guarda como un `ajuste` con nota. Si la diferencia es 0 "
        "no se crea ningún movimiento (`changed=false`)."
    ),
    responses=PRODUCT_ERRORS,
)
def stock_count(
    product_id: int, data: StockCount, db: DbSession, admin: AdminUser
) -> StockCountResult:
    return stock_service.count_stock(db, admin, product_id, data.counted, data.note)
