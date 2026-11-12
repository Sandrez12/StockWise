from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Response, status
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError

from app.deps import AdminUser, DbSession, StaffUser
from app.models import Category, Product, UserRole
from app.schemas import ErrorResponse, Page, ProductCreate, ProductRead, ProductUpdate

router = APIRouter(
    prefix="/products",
    tags=["Productos"],
    responses={
        401: {"model": ErrorResponse, "description": "Token ausente, inválido o expirado"},
        403: {"model": ErrorResponse, "description": "Permisos insuficientes"},
    },
)

NOT_FOUND = {404: {"model": ErrorResponse, "description": "Producto no encontrado"}}
CONFLICT = {409: {"model": ErrorResponse, "description": "SKU duplicado"}}
INVALID = {422: {"model": ErrorResponse, "description": "Datos inválidos"}}

def _escape_like(text: str) -> str:
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _require_active_category(db: DbSession, category_id: int) -> None:
    category = db.get(Category, category_id)
    if category is None or not category.is_active:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "La categoría no existe o está inactiva"
        )


def _sku_taken(db: DbSession, sku: str, exclude_id: int | None = None) -> bool:
    query = select(Product.id).where(Product.sku == sku)
    if exclude_id is not None:
        query = query.where(Product.id != exclude_id)
    return db.scalar(query) is not None


def _duplicate_sku() -> HTTPException:
    return HTTPException(status.HTTP_409_CONFLICT, "Ya existe un producto con ese SKU")


@router.post(
    "",
    response_model=ProductRead,
    status_code=status.HTTP_201_CREATED,
    summary="Crear producto",
    description=(
        "Solo administradores. El SKU se normaliza a mayúsculas y es único. "
        "El stock nace en 0 y solo cambia con movimientos de stock."
    ),
    responses={**CONFLICT, **INVALID},
)
def create_product(data: ProductCreate, db: DbSession, _admin: AdminUser) -> Product:
    _require_active_category(db, data.category_id)
    if _sku_taken(db, data.sku):
        raise _duplicate_sku()
    product = Product(
        sku=data.sku,
        name=data.name,
        description=data.description,
        price=data.price,
        min_stock=data.min_stock,
        category_id=data.category_id,
        stock=0,
    )
    db.add(product)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise _duplicate_sku() from None
    db.refresh(product)
    return product


@router.get(
    "",
    response_model=Page[ProductRead],
    summary="Listar productos",
    description=(
        "Administradores y operadores. Por defecto solo los activos (`include_inactive=true` es "
        "exclusivo de administradores). `q` busca en nombre o SKU. `low_stock=true` devuelve los "
        "productos con `stock <= min_stock` (el umbral es propio de cada producto)."
    ),
)
def list_products(
    db: DbSession,
    user: StaffUser,
    q: Annotated[str | None, Query(max_length=100, description="Texto en nombre o SKU")] = None,
    category_id: Annotated[int | None, Query(description="Filtrar por categoría")] = None,
    low_stock: Annotated[
        bool, Query(description="Solo productos con stock <= min_stock")
    ] = False,
    include_inactive: bool = False,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Page[ProductRead]:
    if include_inactive and user.role != UserRole.ADMIN:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Permisos insuficientes")
    filters = []
    if not include_inactive:
        filters.append(Product.is_active.is_(True))
    if q:
        pattern = f"%{_escape_like(q.strip())}%"
        filters.append(
            or_(Product.name.ilike(pattern, escape="\\"), Product.sku.ilike(pattern, escape="\\"))
        )
    if category_id is not None:
        filters.append(Product.category_id == category_id)
    if low_stock:
        filters.append(Product.stock <= Product.min_stock)
    total = db.scalar(select(func.count()).select_from(Product).where(*filters)) or 0
    rows = db.scalars(
        select(Product).where(*filters).order_by(Product.id).limit(limit).offset(offset)
    )
    return Page(items=list(rows), total=total, limit=limit, offset=offset)


@router.get(
    "/{product_id}",
    response_model=ProductRead,
    summary="Obtener producto",
    description="Los productos inactivos solo los ve un administrador (para el resto, 404).",
    responses=NOT_FOUND,
)
def get_product(product_id: int, db: DbSession, user: StaffUser) -> Product:
    product = db.get(Product, product_id)
    if product is None or (not product.is_active and user.role != UserRole.ADMIN):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Producto no encontrado")
    return product


@router.patch(
    "/{product_id}",
    response_model=ProductRead,
    summary="Actualizar producto",
    description=(
        "Solo administradores. Actualización parcial. **El stock no se puede editar aquí** "
        "(enviar `stock` devuelve 422): solo cambia con movimientos."
    ),
    responses={**NOT_FOUND, **CONFLICT, **INVALID},
)
def update_product(
    product_id: int, data: ProductUpdate, db: DbSession, _admin: AdminUser
) -> Product:
    product = db.get(Product, product_id)
    if product is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Producto no encontrado")
    # Campos obligatorios en la base: un null explícito equivale a "no cambiar".
    changes = {
        k: v
        for k, v in data.model_dump(exclude_unset=True).items()
        if v is not None or k == "description"
    }
    if "category_id" in changes and changes["category_id"] != product.category_id:
        _require_active_category(db, changes["category_id"])
    if "sku" in changes and _sku_taken(db, changes["sku"], exclude_id=product.id):
        raise _duplicate_sku()
    for field, value in changes.items():
        setattr(product, field, value)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise _duplicate_sku() from None
    db.refresh(product)
    return product


@router.delete(
    "/{product_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Borrar (desactivar) producto",
    description="Borrado lógico: pone `is_active=false`; conserva el historial de movimientos. Idempotente.",
    responses=NOT_FOUND,
)
def delete_product(product_id: int, db: DbSession, _admin: AdminUser) -> Response:
    product = db.get(Product, product_id)
    if product is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Producto no encontrado")
    if product.is_active:
        product.is_active = False
        db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
