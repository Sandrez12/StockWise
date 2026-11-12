import os
import re
from decimal import Decimal
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from app.config import get_settings
from app.database import SessionLocal
from app.main import app
from app.models import Category, Product, User, UserRole
from app.security import hash_password

_SAFE_NAME = re.compile(r"^[a-z0-9_]+_test$")


@pytest.fixture(scope="session")
def test_database():
    """Garantiza que exista la base de pruebas y devuelve su nombre.

    Se omite si no hay credenciales TEST_POSTGRES_* y se niega a continuar
    si el nombre de la base no termina en _test, para no tocar datos reales.
    """
    if os.environ.get("STOCKWISE_INTEGRATION") != "1":
        pytest.skip(
            "Sin credenciales de prueba: define TEST_POSTGRES_USER y "
            "TEST_POSTGRES_PASSWORD o crea backend/.env.test"
        )
    settings = get_settings()
    name = settings.postgres_db
    if not _SAFE_NAME.match(name):
        pytest.fail(
            f"La base de pruebas '{name}' no es segura: debe terminar en _test "
            "y usar solo minúsculas, dígitos y guiones bajos."
        )

    admin = create_engine(
        settings.database_url.set(database="postgres"),
        isolation_level="AUTOCOMMIT",
    )
    try:
        with admin.connect() as conn:
            exists = conn.execute(
                text("SELECT 1 FROM pg_database WHERE datname = :n"), {"n": name}
            ).scalar()
            if not exists:
                conn.execute(text(f'CREATE DATABASE "{name}"'))
    finally:
        admin.dispose()
    return name


# --- Fixtures para pruebas de la API (esquema migrado y tablas vacías) -------

_BACKEND = Path(__file__).resolve().parents[2]
TEST_PASSWORD = "contraseña-de-prueba-123"


@pytest.fixture(scope="module")
def schema(test_database):
    """Base _test con el esquema recreado y migrado hasta head (una vez por módulo)."""
    engine = create_engine(get_settings().database_url)
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
    engine.dispose()
    cfg = Config(str(_BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(_BACKEND / "alembic"))
    command.upgrade(cfg, "head")


@pytest.fixture
def db(schema):
    """Sesión de pruebas; antes de cada prueba deja todas las tablas vacías."""
    with SessionLocal() as session:
        session.execute(
            text(
                "TRUNCATE stock_movements, products, categories, users "
                "RESTART IDENTITY CASCADE"
            )
        )
        session.commit()
        yield session


@pytest.fixture
def client(db):
    return TestClient(app)


@pytest.fixture
def make_user(db):
    def _make(email="user@example.com", role=UserRole.OPERATOR, is_active=True,
              password=TEST_PASSWORD, full_name="Usuario de Prueba"):
        user = User(
            email=email,
            full_name=full_name,
            hashed_password=hash_password(password),
            role=role,
            is_active=is_active,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user

    return _make


@pytest.fixture
def login(client):
    """Devuelve cabeceras Authorization tras iniciar sesión por la API."""

    def _login(email, password=TEST_PASSWORD):
        response = client.post("/auth/login", data={"username": email, "password": password})
        assert response.status_code == 200, response.text
        return {"Authorization": f"Bearer {response.json()['access_token']}"}

    return _login


@pytest.fixture
def admin_headers(make_user, login):
    make_user("admin@example.com", UserRole.ADMIN)
    return login("admin@example.com")


@pytest.fixture
def operator_headers(make_user, login):
    make_user("operator@example.com", UserRole.OPERATOR)
    return login("operator@example.com")


@pytest.fixture
def make_category(db):
    def _make(name="Bebidas", is_active=True, description=None):
        category = Category(name=name, is_active=is_active, description=description)
        db.add(category)
        db.commit()
        db.refresh(category)
        return category

    return _make


@pytest.fixture
def make_product(db, make_category):
    def _make(sku="SKU-1", name="Agua", price="1.50", stock=0, is_active=True, category=None,
              min_stock=0):
        category = category or make_category(f"Cat de {sku}")
        product = Product(
            sku=sku, name=name, price=Decimal(price), stock=stock, min_stock=min_stock,
            is_active=is_active, category_id=category.id,
        )
        db.add(product)
        db.commit()
        db.refresh(product)
        return product

    return _make
