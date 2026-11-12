import os
from dataclasses import dataclass, field
from functools import lru_cache

from dotenv import load_dotenv
from sqlalchemy.engine import URL

load_dotenv()

_REQUIRED = (
    "POSTGRES_USER",
    "POSTGRES_PASSWORD",
    "POSTGRES_HOST",
    "POSTGRES_PORT",
    "POSTGRES_DB",
    "SECRET_KEY",
)

MIN_SECRET_KEY_LENGTH = 32
DEFAULT_ACCESS_TOKEN_EXPIRE_MINUTES = 30


class ConfigError(RuntimeError):
    """Configuración de entorno ausente o inválida."""


@dataclass(frozen=True)
class Settings:
    postgres_user: str
    postgres_password: str = field(repr=False)
    postgres_host: str
    postgres_port: int
    postgres_db: str
    secret_key: str = field(repr=False)
    access_token_expire_minutes: int = DEFAULT_ACCESS_TOKEN_EXPIRE_MINUTES

    @property
    def database_url(self) -> URL:
        return URL.create(
            "postgresql+psycopg",
            username=self.postgres_user,
            password=self.postgres_password,
            host=self.postgres_host,
            port=self.postgres_port,
            database=self.postgres_db,
        )


def _positive_int(name: str, raw: str) -> int:
    try:
        value = int(raw)
    except ValueError:
        raise ConfigError(f"{name} debe ser un entero.") from None
    if value <= 0:
        raise ConfigError(f"{name} debe ser un entero positivo.")
    return value


@lru_cache
def get_settings() -> Settings:
    missing = [name for name in _REQUIRED if not os.getenv(name)]
    if missing:
        raise ConfigError(
            f"Faltan variables de entorno: {', '.join(missing)}. "
            "Copia backend/.env.example a backend/.env y complétalo."
        )
    port = _positive_int("POSTGRES_PORT", os.environ["POSTGRES_PORT"])

    secret_key = os.environ["SECRET_KEY"]
    if len(secret_key) < MIN_SECRET_KEY_LENGTH:
        raise ConfigError(
            f"SECRET_KEY debe tener al menos {MIN_SECRET_KEY_LENGTH} caracteres "
            f"(tiene {len(secret_key)}). Genera una con: "
            'python -c "import secrets; print(secrets.token_hex(32))"'
        )

    expire = _positive_int(
        "ACCESS_TOKEN_EXPIRE_MINUTES",
        os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES")
        or str(DEFAULT_ACCESS_TOKEN_EXPIRE_MINUTES),
    )
    return Settings(
        postgres_user=os.environ["POSTGRES_USER"],
        postgres_password=os.environ["POSTGRES_PASSWORD"],
        postgres_host=os.environ["POSTGRES_HOST"],
        postgres_port=port,
        postgres_db=os.environ["POSTGRES_DB"],
        secret_key=secret_key,
        access_token_expire_minutes=expire,
    )
