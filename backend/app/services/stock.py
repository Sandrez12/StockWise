"""Lógica de movimientos de stock.

Toda modificación del stock pasa por `_apply`, que en UNA transacción:

1. bloquea la fila del producto (`SELECT ... FOR UPDATE`),
2. valida sobre el valor ya bloqueado (no sobre una lectura previa),
3. actualiza `products.stock`,
4. inserta el movimiento con `stock_after`,
5. confirma (el commit libera el bloqueo).

Dos peticiones sobre el mismo producto se serializan en el paso 1, así que nunca
operan con un stock desactualizado. El CHECK `stock >= 0` de la base es solo la
red de seguridad si alguien se saltara este módulo.
"""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.errors import ApiError
from app.models import MovementType, Product, StockMovement, User
from app.schemas import MAX_INT, StockCountResult


def _locked_active_product(db: Session, product_id: int) -> Product:
    product = db.execute(
        select(Product)
        .where(Product.id == product_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).scalar_one_or_none()
    if product is None:
        raise ApiError(404, "Producto no encontrado", "not_found")
    if not product.is_active:
        raise ApiError(409, "El producto está inactivo", "inactive_product")
    return product


def _signed(movement_type: MovementType, quantity: int) -> int:
    return -quantity if movement_type == MovementType.SALIDA else quantity


def _apply(
    db: Session,
    product: Product,
    movement_type: MovementType,
    quantity: int,
    reason: str,
    user: User,
) -> StockMovement:
    """Aplica un movimiento sobre un producto YA bloqueado. No hace commit."""
    new_stock = product.stock + _signed(movement_type, quantity)
    if new_stock < 0:
        raise ApiError(
            409,
            f"Stock insuficiente: hay {product.stock} y el movimiento lo dejaría en {new_stock}",
            "insufficient_stock",
        )
    if new_stock > MAX_INT:
        raise ApiError(409, "El stock resultante supera el máximo admitido", "stock_limit_exceeded")
    product.stock = new_stock
    movement = StockMovement(
        product_id=product.id,
        user_id=user.id,
        type=movement_type,
        quantity=quantity,
        stock_after=new_stock,
        reason=reason,
        # clock_timestamp() (no now()): la hora real del insert, tomada con el bloqueo ya
        # adquirido, para que created_at sea monótona por producto aunque haya esperas.
        created_at=func.clock_timestamp(),
    )
    db.add(movement)
    return movement


def register_movement(
    db: Session,
    user: User,
    product_id: int,
    movement_type: MovementType,
    quantity: int,
    reason: str,
) -> StockMovement:
    try:
        product = _locked_active_product(db, product_id)
        movement = _apply(db, product, movement_type, quantity, reason, user)
        db.commit()
    except BaseException:
        db.rollback()
        raise
    db.refresh(movement)
    return movement


def count_stock(
    db: Session, user: User, product_id: int, counted: int, note: str | None
) -> StockCountResult:
    """Conteo físico: la diferencia se calcula bajo bloqueo y se registra como ajuste."""
    try:
        product = _locked_active_product(db, product_id)
        previous = product.stock
        difference = counted - previous
        if difference == 0:
            db.rollback()  # libera el bloqueo; no hay nada que registrar
            return StockCountResult(
                product_id=product_id,
                previous_stock=previous,
                counted=counted,
                difference=0,
                changed=False,
                message="El conteo coincide con el stock registrado; no se creó ningún movimiento",
            )
        reason = f"Conteo físico: {note}" if note else "Conteo físico"
        movement = _apply(db, product, MovementType.AJUSTE, difference, reason, user)
        db.commit()
    except BaseException:
        db.rollback()
        raise
    db.refresh(movement)
    return StockCountResult(
        product_id=product_id,
        previous_stock=previous,
        counted=counted,
        difference=difference,
        changed=True,
        message=f"Ajuste de {difference:+d} unidades registrado",
        movement=movement,
    )
