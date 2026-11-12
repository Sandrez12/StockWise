import pytest
from sqlalchemy.engine import make_url

from app.config import ConfigError, get_settings

VARS = (
    "POSTGRES_USER",
    "POSTGRES_PASSWORD",
    "POSTGRES_HOST",
    "POSTGRES_PORT",
    "POSTGRES_DB",
)


@pytest.fixture(autouse=True)
def clean_settings_cache(monkeypatch):
    """Limpia la caché de get_settings antes y después de cada caso.

    Depende de monkeypatch para que el vaciado ocurra antes de restaurar
    las variables de entorno.
    """
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def set_env(monkeypatch, **overrides):
    values = {
        "POSTGRES_USER": "user",
        "POSTGRES_PASSWORD": "pass",
        "POSTGRES_HOST": "db.local",
        "POSTGRES_PORT": "5433",
        "POSTGRES_DB": "mydb",
    }
    values.update(overrides)
    for name, value in values.items():
        monkeypatch.setenv(name, value)


def test_valid_config_builds_url(monkeypatch):
    set_env(monkeypatch)
    url = get_settings().database_url
    assert url.drivername == "postgresql+psycopg"
    assert url.username == "user"
    assert url.host == "db.local"
    assert url.port == 5433
    assert url.database == "mydb"


def test_missing_variable_names_it(monkeypatch):
    set_env(monkeypatch)
    monkeypatch.delenv("POSTGRES_DB")
    with pytest.raises(ConfigError, match="POSTGRES_DB"):
        get_settings()


def test_empty_variable_is_missing(monkeypatch):
    set_env(monkeypatch, POSTGRES_USER="")
    with pytest.raises(ConfigError, match="POSTGRES_USER"):
        get_settings()


def test_all_missing_are_listed(monkeypatch):
    for name in VARS:
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(ConfigError) as exc:
        get_settings()
    for name in VARS:
        assert name in str(exc.value)


def test_non_integer_port(monkeypatch):
    set_env(monkeypatch, POSTGRES_PORT="abc")
    with pytest.raises(ConfigError, match="POSTGRES_PORT"):
        get_settings()


def test_password_with_special_characters_is_escaped(monkeypatch):
    password = "p@ss:w/rd#1"
    set_env(monkeypatch, POSTGRES_PASSWORD=password)
    url = get_settings().database_url
    rendered = url.render_as_string(hide_password=False)

    # Los caracteres reservados quedan codificados en la cadena...
    assert "p%40ss%3Aw%2Frd%231" in rendered
    assert password not in rendered
    # ...el único "@" sin codificar separa credenciales y host...
    assert rendered.count("@") == 1
    # ...y al reinterpretarla se recupera la contraseña original.
    assert make_url(rendered).password == password
