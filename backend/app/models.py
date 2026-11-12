"""Modelos SQLAlchemy 2 de StockWise.

Las reglas de integridad (stock no negativo, SKU único, cantidades válidas) se
declaran también como restricciones de la base de datos: la aplicación no es la
única que puede escribir, y un fallo de lógica no debe poder corromper el stock.
"""

import enum
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class UserRole(str, enum.Enum):
    ADMIN = "admin"
    OPERATOR = "operator"


class MovementType(str, enum.Enum):
    ENTRADA = "entrada"
    SALIDA = "salida"
    AJUSTE = "ajuste"


def _enum(enum_cls: type[enum.Enum], name: str) -> Enum:
    # Se guardan los valores en minúscula ("admin"), no los nombres del enum.
    return Enum(enum_cls, name=name, values_callable=lambda e: [m.value for m in e])


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True)
    full_name: Mapped[str] = mapped_column(String(150))
    hashed_password: Mapped[str] = mapped_column(String(255))
    role: Mapped[UserRole] = mapped_column(
        _enum(UserRole, "user_role"), default=UserRole.OPERATOR
    )
    is_active: Mapped[bool] = mapped_column(default=True, server_default="true")

    movements: Mapped[list["StockMovement"]] = relationship(back_populates="user")


class Category(TimestampMixin, Base):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    description: Mapped[str | None] = mapped_column(Text)

    products: Mapped[list["Product"]] = relationship(back_populates="category")


class Product(TimestampMixin, Base):
    __tablename__ = "products"
    __table_args__ = (
        CheckConstraint("stock >= 0", name="ck_products_stock_non_negative"),
        CheckConstraint("price >= 0", name="ck_products_price_non_negative"),
        Index("ix_products_category_id", "category_id"),
        Index("ix_products_name", "name"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    sku: Mapped[str] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    price: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    stock: Mapped[int] = mapped_column(default=0, server_default="0")
    is_active: Mapped[bool] = mapped_column(default=True, server_default="true")
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id", ondelete="RESTRICT"))

    category: Mapped[Category] = relationship(back_populates="products")
    movements: Mapped[list["StockMovement"]] = relationship(back_populates="product")


class StockMovement(Base):
    """Movimiento de inventario. Es un registro de auditoría: no se actualiza.

    `quantity` es siempre entero distinto de cero: positivo en entrada y salida
    (el tipo indica el sentido) y con signo en ajuste (+ suma, - resta).
    """

    __tablename__ = "stock_movements"
    __table_args__ = (
        CheckConstraint(
            "(type = 'ajuste' AND quantity <> 0) OR (type <> 'ajuste' AND quantity > 0)",
            name="ck_stock_movements_quantity_valid",
        ),
        Index("ix_stock_movements_product_id_created_at", "product_id", "created_at"),
        Index("ix_stock_movements_user_id", "user_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="RESTRICT"))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    type: Mapped[MovementType] = mapped_column(_enum(MovementType, "movement_type"))
    quantity: Mapped[int]
    reason: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    product: Mapped[Product] = relationship(back_populates="movements")
    user: Mapped[User] = relationship(back_populates="movements")
