import os
from pathlib import Path

from dotenv import dotenv_values

# Las pruebas NUNCA usan backend/.env. Se sobrescriben (no setdefault) las
# cinco variables POSTGRES_* antes de importar la app; como config.py usa
# load_dotenv() sin override, el .env local ya no puede aplicarse.
#
# Valores de la base de pruebas, por orden de prioridad:
#   1. variables de entorno TEST_POSTGRES_* (CI o shell),
#   2. backend/.env.test (local, ignorado por git),
#   3. valores falsos: solo valen para las pruebas unitarias.
_BACKEND = Path(__file__).resolve().parent.parent
_test = {
    **dotenv_values(_BACKEND / ".env.test"),
    **{k: v for k, v in os.environ.items() if k.startswith("TEST_POSTGRES_")},
}

_integration = bool(_test.get("TEST_POSTGRES_USER") and _test.get("TEST_POSTGRES_PASSWORD"))

os.environ["POSTGRES_USER"] = _test.get("TEST_POSTGRES_USER") or "test_user"
os.environ["POSTGRES_PASSWORD"] = _test.get("TEST_POSTGRES_PASSWORD") or "test_password"
os.environ["POSTGRES_HOST"] = _test.get("TEST_POSTGRES_HOST") or "localhost"
os.environ["POSTGRES_PORT"] = _test.get("TEST_POSTGRES_PORT") or "5432"
os.environ["POSTGRES_DB"] = _test.get("TEST_POSTGRES_DB") or (
    "stockwise_test" if _integration else "test_db"
)

# Indica a las pruebas de integración si hay credenciales reales de prueba.
os.environ["STOCKWISE_INTEGRATION"] = "1" if _integration else "0"
