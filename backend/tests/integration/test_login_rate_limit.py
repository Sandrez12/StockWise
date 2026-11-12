import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.ratelimit import login_limiter

pytestmark = pytest.mark.integration

GOOD = "contraseña-de-prueba-123"


def _fail(client, email="ana@example.com"):
    return client.post("/auth/login", data={"username": email, "password": "incorrecta-123456"})


def test_sixth_attempt_is_429_with_code_and_retry_after(client, make_user):
    make_user("ana@example.com")
    for _ in range(5):
        assert _fail(client).status_code == 401
    r = _fail(client)
    assert r.status_code == 429
    body = r.json()
    assert body["code"] == "too_many_requests"
    assert int(r.headers["retry-after"]) > 0
    assert int(r.headers["retry-after"]) <= 15 * 60 + 1


def test_correct_password_is_also_blocked_while_locked(client, make_user):
    make_user("ana@example.com")
    for _ in range(5):
        _fail(client)
    r = client.post("/auth/login", data={"username": "ana@example.com", "password": GOOD})
    assert r.status_code == 429


def test_unknown_email_is_limited_the_same_way(client):
    for _ in range(5):
        assert _fail(client, "fantasma@example.com").status_code == 401
    assert _fail(client, "fantasma@example.com").status_code == 429


def test_other_email_and_other_ip_are_not_affected(client, make_user):
    make_user("ana@example.com")
    make_user("beto@example.com")
    for _ in range(5):
        _fail(client)
    assert _fail(client).status_code == 429
    ok = client.post("/auth/login", data={"username": "beto@example.com", "password": GOOD})
    assert ok.status_code == 200
    other_ip = TestClient(app, client=("10.9.9.9", 5000))
    ok = other_ip.post("/auth/login", data={"username": "ana@example.com", "password": GOOD})
    assert ok.status_code == 200


def test_successful_login_resets_the_counter(client, make_user):
    make_user("ana@example.com")
    for _ in range(4):
        _fail(client)
    assert client.post("/auth/login", data={"username": "ana@example.com", "password": GOOD}).status_code == 200
    for _ in range(4):
        assert _fail(client).status_code == 401


def test_lock_expires_after_window(client, make_user, monkeypatch):
    make_user("ana@example.com")
    now = [1000.0]
    monkeypatch.setattr(login_limiter, "_clock", lambda: now[0])
    for _ in range(5):
        _fail(client)
    assert _fail(client).status_code == 429
    now[0] += 15 * 60
    ok = client.post("/auth/login", data={"username": "ana@example.com", "password": GOOD})
    assert ok.status_code == 200


def test_429_response_does_not_leak_account_existence(client, make_user):
    make_user("ana@example.com")
    for _ in range(5):
        _fail(client, "ana@example.com")
        _fail(client, "fantasma@example.com")
    real = _fail(client, "ana@example.com")
    ghost = _fail(client, "fantasma@example.com")
    assert real.status_code == ghost.status_code == 429
    assert real.json() == ghost.json()
