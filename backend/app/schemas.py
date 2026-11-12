"""Esquemas Pydantic de entrada y salida. Ninguno de salida incluye el hash."""

import re
from datetime import datetime
from decimal import Decimal
from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

from app.models import MovementType, UserRole

T = TypeVar("T")

MAX_INT = 2_147_483_647  # límite de INTEGER en PostgreSQL

_SKU_PATTERN =re.compile(r"^[A-Z0-9][A-Z0-9._-]*$")


class ErrorDetail(BaseModel):
    field: str
    message: str


class ErrorResponse(BaseModel):
    """Formato único de error de toda la API."""

    detail: str = Field(description="Mensaje legible")
    code: str = Field(description="Código estable, p. ej. not_found, conflict, validation_error")
    errors: list[ErrorDetail] | None = Field(
        default=None, description="Solo en errores de validación: un elemento por campo"
    )


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int = Field(description="Total de elementos que cumplen el filtro")
    limit: int
    offset: int

MIN_PASSWORD_LENGTH = 12
MAX_PASSWORD_LENGTH = 128


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int = Field(description="Segundos hasta que el token expira")


class UserCreate(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=1, max_length=150)
    password: str = Field(min_length=MIN_PASSWORD_LENGTH, max_length=MAX_PASSWORD_LENGTH)
    role: UserRole = UserRole.OPERATOR

    @field_validator("email")
    @classmethod
    def _normalize_email(cls, value: str) -> str:
        return value.strip().lower()

    @field_validator("full_name")
    @classmethod
    def _strip_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("El nombre no puede estar vacío")
        return value


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: EmailStr
    full_name: str
    role: UserRole
    is_active: bool
    created_at: datetime


class UserRoleUpdate(BaseModel):
    role: UserRole


class UserActiveUpdate(BaseModel):
    is_active: bool


# --- Catálogo ----------------------------------------------------------------


def _clean_text(value: str) -> str:
    value = value.strip()
    if not value:
        raise ValueError("No puede estar vacío")
    return value


class CategoryCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=1000)

    @field_validator("name")
    @classmethod
    def _strip_name(cls, value: str) -> str:
        return _clean_text(value)


class CategoryUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=1000)
    is_active: bool | None = None

    @field_validator("name")
    @classmethod
    def _strip_name(cls, value: str | None) -> str | None:
        return None if value is None else _clean_text(value)


class CategoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime


Money = Field(ge=0, max_digits=12, decimal_places=2, description="Precio, máximo 2 decimales")


def _normalize_sku(value: str) -> str:
    value = value.strip().upper()
    if not _SKU_PATTERN.match(value):
        raise ValueError("El SKU solo admite letras, dígitos, punto, guion y guion bajo")
    return value


class ProductCreate(BaseModel):
    """El stock no se envía: nace en 0 y solo cambia con movimientos."""

    model_config = ConfigDict(extra="forbid")

    sku: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    price: Decimal = Money
    min_stock: int = Field(
        default=0, ge=0, le=MAX_INT, description="Umbral de stock bajo: low_stock = stock <= min_stock"
    )
    category_id: int

    @field_validator("sku")
    @classmethod
    def _sku(cls, value: str) -> str:
        return _normalize_sku(value)

    @field_validator("name")
    @classmethod
    def _name(cls, value: str) -> str:
        return _clean_text(value)


class ProductUpdate(BaseModel):
    """Actualización parcial. `stock` no existe aquí: enviarlo es un error 422."""

    model_config = ConfigDict(extra="forbid")

    sku: str | None = Field(default=None, min_length=1, max_length=64)
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    price: Decimal | None = Field(
        default=None, ge=0, max_digits=12, decimal_places=2, description="Precio, máximo 2 decimales"
    )
    min_stock: int | None = Field(default=None, ge=0, le=MAX_INT)
    category_id: int | None = None
    is_active: bool | None = None

    @field_validator("sku")
    @classmethod
    def _sku(cls, value: str | None) -> str | None:
        return None if value is None else _normalize_sku(value)

    @field_validator("name")
    @classmethod
    def _name(cls, value: str | None) -> str | None:
        return None if value is None else _clean_text(value)


class ProductRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    sku: str
    name: str
    description: str | None
    price: Decimal
    stock: int
    min_stock: int
    is_active: bool
    category_id: int
    created_at: datetime
    updated_at: datetime


# --- Movimientos de stock ----------------------------------------------------


class MovementCreate(BaseModel):
    """El usuario del movimiento sale del token: enviar `user_id` es un error 422."""

    model_config = ConfigDict(extra="forbid")

    product_id: int
    type: MovementType
    quantity: int = Field(
        ge=-MAX_INT,
        le=MAX_INT,
        description=(
            "Entero distinto de cero. En `entrada` y `salida` debe ser positivo (el tipo indica "
            "el sentido); en `ajuste` lleva signo (+ suma, - resta)."
        ),
    )
    reason: str = Field(min_length=1, max_length=255, description="Motivo del movimiento")

    @field_validator("reason")
    @classmethod
    def _reason(cls, value: str) -> str:
        return _clean_text(value)

    @model_validator(mode="after")
    def _quantity_matches_type(self) -> "MovementCreate":
        if self.type == MovementType.AJUSTE:
            if self.quantity == 0:
                raise ValueError("En un ajuste la cantidad no puede ser 0")
        elif self.quantity <= 0:
            raise ValueError("En entrada y salida la cantidad debe ser positiva")
        return self


class MovementRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    product_id: int
    user_id: int
    type: MovementType
    quantity: int
    stock_after: int = Field(description="Stock del producto justo después de este movimiento")
    reason: str
    created_at: datetime


class StockCount(BaseModel):
    model_config = ConfigDict(extra="forbid")

    counted: int = Field(ge=0, le=MAX_INT, description="Unidades contadas físicamente")
    note: str | None = Field(default=None, max_length=200, description="Nota opcional del conteo")

    @field_validator("note")
    @classmethod
    def _note(cls, value: str | None) -> str | None:
        return value.strip() or None if value is not None else None


class StockCountResult(BaseModel):
    product_id: int
    previous_stock: int
    counted: int
    difference: int = Field(description="counted - previous_stock")
    changed: bool = Field(description="False si no hubo diferencia y no se creó movimiento")
    message: str
    movement: MovementRead | None = None
