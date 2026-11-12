from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError

from app.config import get_settings

pytestmark = pytest.mark.integration

BACKEND = Path(__file__).resolve().parents[2]


def _alembic_config() -> Config:
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "alembic"))
    return cfg


@pytest.fixture
def engine(test_database):
    eng = create_engine(get_settings().database_url)
    yield eng
    eng.dispose()


@pytest.fixture
def migrated(engine):
    """Base _test vacía (esquema public recreado) migrada hasta head.

    Seguro: test_database ya garantiza que la base termina en _test.
    """
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
    command.upgrade(_alembic_config(), "head")
    yield engine


def _insert_category(conn) -> int:
    return conn.execute(
        text("INSERT INTO categories (name) VALUES ('Bebidas') RETURNING id")
    ).scalar()


def _insert_product(conn, category_id, sku="SKU-1", stock=0):
    return conn.execute(
        text(
            "INSERT INTO products (sku, name, price, stock, category_id) "
            "VALUES (:sku, 'Agua', 1.50, :stock, :cat) RETURNING id"
        ),
        {"sku": sku, "stock": stock, "cat": category_id},
    ).scalar()


def test_upgrade_creates_all_tables(migrated):
    tables = set(inspect(migrated).get_table_names())
    assert {"users", "categories", "products", "stock_movements", "alembic_version"} <= tables


def test_models_match_migrations(migrated):
    # Falla si los modelos tienen cambios sin migración (autogenerate detectaría diferencias).
    command.check(_alembic_config())


def test_duplicate_sku_is_rejected(migrated):
    with pytest.raises(IntegrityError, match="uq_products_sku"):
        with migrated.begin() as conn:
            cat = _insert_category(conn)
            _insert_product(conn, cat, sku="DUP")
            _insert_product(conn, cat, sku="DUP")


def test_negative_stock_is_rejected(migrated):
    with pytest.raises(IntegrityError, match="ck_products_stock_non_negative"):
        with migrated.begin() as conn:
            _insert_product(conn, _insert_category(conn), stock=-1)


def test_negative_min_stock_is_rejected(migrated):
    with pytest.raises(IntegrityError, match="ck_products_min_stock_non_negative"):
        with migrated.begin() as conn:
            cat = _insert_category(conn)
            conn.execute(
                text(
                    "INSERT INTO products (sku, name, price, min_stock, category_id) "
                    "VALUES ('P', 'X', 1, -1, :cat)"
                ),
                {"cat": cat},
            )


def test_min_stock_defaults_to_zero(migrated):
    with migrated.begin() as conn:
        product = _insert_product(conn, _insert_category(conn))
        assert conn.execute(
            text("SELECT min_stock FROM products WHERE id = :p"), {"p": product}
        ).scalar() == 0


def test_negative_price_is_rejected(migrated):
    with pytest.raises(IntegrityError, match="ck_products_price_non_negative"):
        with migrated.begin() as conn:
            cat = _insert_category(conn)
            conn.execute(
                text(
                    "INSERT INTO products (sku, name, price, category_id) "
                    "VALUES ('P', 'X', -1, :cat)"
                ),
                {"cat": cat},
            )


@pytest.mark.parametrize(
    "type_, quantity",
    [("entrada", 0), ("salida", -5), ("ajuste", 0)],
)
def test_invalid_movement_quantity_is_rejected(migrated, type_, quantity):
    with pytest.raises(IntegrityError, match="ck_stock_movements_quantity_valid"):
        with migrated.begin() as conn:
            product = _insert_product(conn, _insert_category(conn))
            user = conn.execute(
                text(
                    "INSERT INTO users (email, full_name, hashed_password, role) "
                    "VALUES ('a@b.c', 'A', 'x', 'admin') RETURNING id"
                )
            ).scalar()
            conn.execute(
                text(
                    "INSERT INTO stock_movements (product_id, user_id, type, quantity, reason) "
                    "VALUES (:p, :u, :t, :q, 'prueba')"
                ),
                {"p": product, "u": user, "t": type_, "q": quantity},
            )


def test_negative_adjustment_is_allowed(migrated):
    with migrated.begin() as conn:
        product = _insert_product(conn, _insert_category(conn), stock=5)
        user = conn.execute(
            text(
                "INSERT INTO users (email, full_name, hashed_password, role) "
                "VALUES ('a@b.c', 'A', 'x', 'operator') RETURNING id"
            )
        ).scalar()
        conn.execute(
            text(
                "INSERT INTO stock_movements (product_id, user_id, type, quantity, reason) "
                "VALUES (:p, :u, 'ajuste', -2, 'merma')"
            ),
            {"p": product, "u": user},
        )


def test_invalid_role_is_rejected(migrated):
    with pytest.raises(Exception, match="user_role"):
        with migrated.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO users (email, full_name, hashed_password, role) "
                    "VALUES ('a@b.c', 'A', 'x', 'root')"
                )
            )


def test_cannot_delete_product_with_movements(migrated):
    with pytest.raises(IntegrityError):
        with migrated.begin() as conn:
            product = _insert_product(conn, _insert_category(conn), stock=1)
            user = conn.execute(
                text(
                    "INSERT INTO users (email, full_name, hashed_password, role) "
                    "VALUES ('a@b.c', 'A', 'x', 'admin') RETURNING id"
                )
            ).scalar()
            conn.execute(
                text(
                    "INSERT INTO stock_movements (product_id, user_id, type, quantity, reason) "
                    "VALUES (:p, :u, 'entrada', 1, 'x')"
                ),
                {"p": product, "u": user},
            )
            conn.execute(text("DELETE FROM products WHERE id = :p"), {"p": product})


def test_downgrade_removes_everything(migrated):
    command.downgrade(_alembic_config(), "base")
    insp = inspect(migrated)
    assert set(insp.get_table_names()) <= {"alembic_version"}
    with migrated.connect() as conn:
        enums = conn.execute(
            text("SELECT typname FROM pg_type WHERE typname IN ('user_role', 'movement_type')")
        ).all()
    assert enums == []
