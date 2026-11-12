import time
from datetime import timedelta

import jwt
import pytest
from sqlalchemy import text

from app.config import get_settings
from app.models import UserRole
from app.security import ALGORITHM, create_access_token

pytestmark = pytest.mark.integration

TEST_PASSWORD = "contraseña-de-prueba-123"  # la misma que usa make_user


def _form(email, password=TEST_PASSWORD):
    return {"username": email, "password": password}


def test_login_ok_returns_bearer_token(client, make_user):
    make_user("ana@example.com")
    r = client.post("/auth/login", data=_form("ana@example.com"))
    assert r.status_code == 200
    body = r.json()
    assert body["token_type"] == "bearer"
    assert body["expires_in"] == 30 * 60
    claims = jwt.decode(body["access_token"], get_settings().secret_key, algorithms=[ALGORITHM])
    assert claims["exp"] - claims["iat"] == 30 * 60


def test_login_is_case_insensitive_on_email(client, make_user):
    make_user("ana@example.com")
    assert client.post("/auth/login", data=_form("ANA@Example.com")).status_code == 200


def test_login_wrong_password_and_unknown_email_look_identical(client, make_user):
    make_user("ana@example.com")
    wrong = client.post("/auth/login", data=_form("ana@example.com", "otra-contraseña-123"))
    unknown = client.post("/auth/login", data=_form("nadie@example.com"))
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json() == {"detail": "Correo o contraseña incorrectos"}


def test_login_inactive_user_gets_same_generic_error(client, make_user):
    make_user("off@example.com", is_active=False)
    r = client.post("/auth/login", data=_form("off@example.com"))
    assert r.status_code == 401
    assert r.json() == {"detail": "Correo o contraseña incorrectos"}


def test_me_returns_current_user_without_hash(client, make_user, login):
    make_user("ana@example.com", UserRole.ADMIN)
    r = client.get("/auth/me", headers=login("ana@example.com"))
    assert r.status_code == 200
    body = r.json()
    assert body["email"] == "ana@example.com"
    assert body["role"] == "admin"
    assert "hashed_password" not in body and "password" not in body
    assert "$argon2" not in r.text


def test_missing_token_is_401(client):
    r = client.get("/auth/me")
    assert r.status_code == 401
    assert r.headers["www-authenticate"] == "Bearer"


def test_expired_token_is_401(client, make_user):
    user = make_user()
    token = create_access_token(str(user.id), expires_delta=timedelta(seconds=-5))
    r = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 401


def test_tampered_token_is_401(client, make_user):
    user = make_user()
    header, _payload, signature = create_access_token(str(user.id)).split(".")
    forged_payload = create_access_token("999999").split(".")[1]
    r = client.get(
        "/auth/me", headers={"Authorization": f"Bearer {header}.{forged_payload}.{signature}"}
    )
    assert r.status_code == 401


def test_token_signed_with_other_key_is_401(client, make_user):
    user = make_user()
    token = jwt.encode(
        {"sub": str(user.id), "exp": time.time() + 600}, "o" * 40, algorithm=ALGORITHM
    )
    assert client.get("/auth/me", headers={"Authorization": f"Bearer {token}"}).status_code == 401


def test_token_for_unknown_user_is_401(client):
    token = create_access_token("12345")
    assert client.get("/auth/me", headers={"Authorization": f"Bearer {token}"}).status_code == 401


def test_deactivated_user_loses_access_with_existing_token(client, make_user, login, db):
    user = make_user("ana@example.com")
    headers = login("ana@example.com")
    assert client.get("/auth/me", headers=headers).status_code == 200
    user.is_active = False
    db.commit()
    assert client.get("/auth/me", headers=headers).status_code == 401


def test_role_is_read_from_database_not_from_token(client, make_user, login, db):
    user = make_user("ana@example.com", UserRole.ADMIN)
    headers = login("ana@example.com")
    assert client.get("/users", headers=headers).status_code == 200
    user.role = UserRole.OPERATOR
    db.commit()
    assert client.get("/users", headers=headers).status_code == 403


def test_password_is_not_stored_in_plaintext(client, db, admin_headers):
    r = client.post(
        "/users",
        headers=admin_headers,
        json={
            "email": "new@example.com",
            "full_name": "Nuevo",
            "password": "una-clave-muy-larga-1",
        },
    )
    assert r.status_code == 201
    stored = db.execute(
        text("SELECT hashed_password FROM users WHERE email = 'new@example.com'")
    ).scalar()
    assert stored.startswith("$argon2")
    assert "una-clave-muy-larga-1" not in stored
