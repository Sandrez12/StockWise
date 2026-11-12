import os
import re

import pytest
from sqlalchemy import create_engine, text

from app.config import get_settings

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
