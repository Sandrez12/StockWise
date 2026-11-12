import pytest
from sqlalchemy import select

from app import cli
from app.models import User, UserRole

pytestmark = pytest.mark.integration

PASSWORD = "clave-del-primer-admin-1"


def test_create_admin_creates_hashed_admin(db):
    user = cli.create_admin(db, " Root@Example.com ", "Root", PASSWORD)
    stored = db.scalar(select(User).where(User.id == user.id))
    assert stored.email == "root@example.com"
    assert stored.role == UserRole.ADMIN
    assert stored.hashed_password.startswith("$argon2")
    assert PASSWORD not in stored.hashed_password


def test_create_admin_rejects_duplicate_short_password_and_bad_email(db):
    cli.create_admin(db, "root@example.com", "Root", PASSWORD)
    with pytest.raises(cli.CliError, match="Ya existe"):
        cli.create_admin(db, "ROOT@example.com", "Otro", PASSWORD)
    with pytest.raises(cli.CliError, match="contraseña"):
        cli.create_admin(db, "b@example.com", "B", "corta")
    with pytest.raises(cli.CliError, match="correo"):
        cli.create_admin(db, "no-es-correo", "B", PASSWORD)


def test_main_prompts_and_creates_admin(db, monkeypatch, capsys):
    answers = {"Correo: ": "cli@example.com", "Nombre completo: ": "Cli"}
    monkeypatch.setattr("builtins.input", lambda prompt="": answers[prompt])
    monkeypatch.setattr("getpass.getpass", lambda prompt="": PASSWORD)
    assert cli.main(["create-admin"]) == 0
    assert "cli@example.com" in capsys.readouterr().out
    assert db.scalar(select(User).where(User.email == "cli@example.com")).role == UserRole.ADMIN


def test_main_rejects_mismatched_passwords(db, monkeypatch, capsys):
    answers = iter([PASSWORD, "otra-distinta-12345"])
    monkeypatch.setattr("getpass.getpass", lambda prompt="": next(answers))
    assert cli.main(["create-admin", "--email", "x@example.com", "--name", "X"]) == 1
    assert "no coinciden" in capsys.readouterr().err
    assert db.scalar(select(User).where(User.email == "x@example.com")) is None


def test_password_cannot_be_passed_as_argument():
    with pytest.raises(SystemExit):
        cli.main(["create-admin", "--password", "secreto"])
