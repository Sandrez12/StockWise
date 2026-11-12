import pytest
from sqlalchemy import text

pytestmark = pytest.mark.integration

NEW_USER = {
    "email": "nuevo@example.com",
    "full_name": "Nuevo Usuario",
    "password": "clave-larga-segura-1",
}


def _assert_no_secrets(response):
    assert "hashed_password" not in response.text
    assert "$argon2" not in response.text
    assert NEW_USER["password"] not in response.text


def test_there_is_no_public_registration(client):
    assert client.post("/users", json=NEW_USER).status_code == 401
    assert client.post("/auth/register", json=NEW_USER).status_code == 404


def test_operator_cannot_manage_users(client, operator_headers):
    assert client.post("/users", json=NEW_USER, headers=operator_headers).status_code == 403
    assert client.get("/users", headers=operator_headers).status_code == 403
    r = client.patch("/users/1/role", json={"role": "admin"}, headers=operator_headers)
    assert r.status_code == 403
    r = client.patch("/users/1/active", json={"is_active": False}, headers=operator_headers)
    assert r.status_code == 403


def test_admin_creates_user_defaulting_to_operator(client, admin_headers):
    r = client.post("/users", json=NEW_USER, headers=admin_headers)
    assert r.status_code == 201
    body = r.json()
    assert body["email"] == "nuevo@example.com"
    assert body["role"] == "operator"
    assert body["is_active"] is True
    _assert_no_secrets(r)


def test_created_user_can_log_in(client, admin_headers):
    client.post("/users", json=NEW_USER, headers=admin_headers)
    r = client.post(
        "/auth/login", data={"username": NEW_USER["email"], "password": NEW_USER["password"]}
    )
    assert r.status_code == 200


def test_email_is_normalized_and_duplicates_conflict(client, admin_headers):
    client.post("/users", json=NEW_USER, headers=admin_headers)
    again = {**NEW_USER, "email": "  NUEVO@Example.com "}
    assert client.post("/users", json=again, headers=admin_headers).status_code == 409


@pytest.mark.parametrize(
    "patch",
    [
        {"email": "no-es-correo"},
        {"password": "corta"},
        {"full_name": "   "},
        {"role": "superuser"},
    ],
)
def test_create_user_validation(client, admin_headers, patch):
    r = client.post("/users", json={**NEW_USER, **patch}, headers=admin_headers)
    assert r.status_code == 422


def test_list_users_paginates_and_hides_hash(client, admin_headers, make_user):
    for i in range(3):
        make_user(f"u{i}@example.com")
    r = client.get("/users", headers=admin_headers)
    assert r.status_code == 200 and len(r.json()) == 4
    _assert_no_secrets(r)
    page = client.get("/users?limit=2&offset=1", headers=admin_headers).json()
    assert [u["id"] for u in page] == [2, 3]
    assert client.get("/users?limit=0", headers=admin_headers).status_code == 422
    assert client.get("/users?limit=101", headers=admin_headers).status_code == 422


def test_admin_changes_role(client, admin_headers, make_user):
    other = make_user("otro@example.com")
    r = client.patch(f"/users/{other.id}/role", json={"role": "admin"}, headers=admin_headers)
    assert r.status_code == 200 and r.json()["role"] == "admin"
    _assert_no_secrets(r)


def test_admin_deactivates_and_reactivates_user(client, admin_headers, make_user):
    other = make_user("otro@example.com")
    r = client.patch(
        f"/users/{other.id}/active", json={"is_active": False}, headers=admin_headers
    )
    assert r.status_code == 200 and r.json()["is_active"] is False
    login = client.post(
        "/auth/login",
        data={"username": "otro@example.com", "password": "contraseña-de-prueba-123"},
    )
    assert login.status_code == 401
    r = client.patch(
        f"/users/{other.id}/active", json={"is_active": True}, headers=admin_headers
    )
    assert r.json()["is_active"] is True


def test_admin_cannot_demote_or_deactivate_self(client, admin_headers, db):
    admin_id = db.execute(
        text("SELECT id FROM users WHERE email = 'admin@example.com'")
    ).scalar()
    r = client.patch(f"/users/{admin_id}/role", json={"role": "operator"}, headers=admin_headers)
    assert r.status_code == 409
    r = client.patch(
        f"/users/{admin_id}/active", json={"is_active": False}, headers=admin_headers
    )
    assert r.status_code == 409


def test_unknown_user_is_404(client, admin_headers):
    r = client.patch("/users/9999/role", json={"role": "admin"}, headers=admin_headers)
    assert r.status_code == 404
    r = client.patch("/users/9999/active", json={"is_active": False}, headers=admin_headers)
    assert r.status_code == 404


def test_invalid_role_value_is_422(client, admin_headers, make_user):
    other = make_user("otro@example.com")
    r = client.patch(f"/users/{other.id}/role", json={"role": "root"}, headers=admin_headers)
    assert r.status_code == 422
