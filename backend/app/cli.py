"""Comandos de consola. Uso (desde backend/):

    python -m app.cli create-admin
"""

import argparse
import getpass
import sys

from pydantic import EmailStr, TypeAdapter, ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import User, UserRole
from app.schemas import MAX_PASSWORD_LENGTH, MIN_PASSWORD_LENGTH
from app.security import hash_password

_email_adapter = TypeAdapter(EmailStr)


class CliError(Exception):
    """Entrada inválida o conflicto; el mensaje se muestra al usuario."""


def create_admin(db: Session, email: str, full_name: str, password: str) -> User:
    try:
        email = _email_adapter.validate_python(email.strip()).lower()
    except ValidationError:
        raise CliError("El correo no es válido.") from None
    if not MIN_PASSWORD_LENGTH <= len(password) <= MAX_PASSWORD_LENGTH:
        raise CliError(
            f"La contraseña debe tener entre {MIN_PASSWORD_LENGTH} y {MAX_PASSWORD_LENGTH} caracteres."
        )
    if db.scalar(select(User.id).where(User.email == email)) is not None:
        raise CliError("Ya existe un usuario con ese correo.")
    user = User(
        email=email,
        full_name=full_name.strip() or "Administrador",
        hashed_password=hash_password(password),
        role=UserRole.ADMIN,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _prompt_password() -> str:
    password = getpass.getpass("Contraseña: ")
    if password != getpass.getpass("Repite la contraseña: "):
        raise CliError("Las contraseñas no coinciden.")
    return password


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    sub = parser.add_subparsers(dest="command", required=True)
    admin = sub.add_parser("create-admin", help="Crea un usuario administrador")
    admin.add_argument("--email", help="Correo (si se omite, se pregunta)")
    admin.add_argument("--name", help="Nombre completo (si se omite, se pregunta)")
    args = parser.parse_args(argv)

    # La contraseña nunca se recibe por argumentos: solo por prompt sin eco.
    try:
        email = args.email or input("Correo: ")
        name = args.name if args.name is not None else input("Nombre completo: ")
        password = _prompt_password()
        from app.database import SessionLocal  # import tardío: exige configuración válida

        with SessionLocal() as db:
            user = create_admin(db, email, name, password)
    except CliError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    print(f"Administrador creado: {user.email} (id {user.id})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
