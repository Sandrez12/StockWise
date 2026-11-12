import os
from dataclasses import dataclass
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
)


class ConfigError(RuntimeError):
    """Configuración de entorno ausente o inválida."""


@dataclass(frozen=True)
class Settings:
    postgres_user: str
    postgres_password: str
    postgres_host: str
    postgres_port: int
    postgres_db: str

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


@lru_cache
def get_settings() -> Settings:
    missing = [name for name in _REQUIRED if not os.getenv(name)]
    if missing:
        raise ConfigError(
            f"Faltan variables de entorno: {', '.join(missing)}. "
            "Copia backend/.env.example a backend/.env."
        )
    try:
        port = int(os.environ["POSTGRES_PORT"])
    except ValueError:
        raise ConfigError("POSTGRES_PORT debe ser un entero.") from None
    return Settings(
        postgres_user=os.environ["POSTGRES_USER"],
        postgres_password=os.environ["POSTGRES_PASSWORD"],
        postgres_host=os.environ["POSTGRES_HOST"],
        postgres_port=port,
        postgres_db=os.environ["POSTGRES_DB"],
    )
