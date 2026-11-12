import pytest
from sqlalchemy import text

pytestmark = pytest.mark.integration


@pytest.fixture
def product(make_product):
    """Producto activo con stock 0 (nace sin movimientos, el invariante se cumple)."""
    return make_product("MOV-1", stock=0)


# --- permisos ---------------------------------------------------------------


def test_requires_authentication(client, product):
    assert client.post("/stock-movements", json={}).status_code == 401
    assert client.get("/stock-movements").status_code == 401
    assert client.post(f"/products/{product.id}/stock-count", json={"counted": 1}).status_code == 401


def test_operator_can_register_entrada_and_salida(client, move, operator_headers, product):
    assert move(operator_headers, product.id, "entrada", 10).status_code == 201
    assert move(operator_headers, product.id, "salida", 4).status_code == 201


def test_operator_cannot_register_ajuste(client, move, operator_headers, product, db):
    r = move(operator_headers, product.id, "ajuste", 5)
    assert r.status_code == 403
    assert db.execute(text("SELECT count(*) FROM stock_movements")).scalar() == 0


def test_admin_can_register_all_types(move, admin_headers, product):
    assert move(admin_headers, product.id, "entrada", 10).status_code == 201
    assert move(admin_headers, product.id, "salida", 1).status_code == 201
    assert move(admin_headers, product.id, "ajuste", -2).status_code == 201
    assert move(admin_headers, product.id, "ajuste", 5).status_code == 201


def test_both_roles_can_read_movements(client, operator_headers, admin_headers):
    assert client.get("/stock-movements", headers=operator_headers).status_code == 200
    assert client.get("/stock-movements", headers=admin_headers).status_code == 200


# --- efecto sobre el stock --------------------------------------------------


def test_movement_updates_stock_and_records_stock_after(
    client, move, admin_headers, product, stock_invariant
):
    r1 = move(admin_headers, product.id, "entrada", 10, "compra").json()
    r2 = move(admin_headers, product.id, "salida", 3, "venta").json()
    r3 = move(admin_headers, product.id, "ajuste", -2, "merma").json()
    r4 = move(admin_headers, product.id, "ajuste", 5, "hallazgo").json()
    assert [m["stock_after"] for m in (r1, r2, r3, r4)] == [10, 7, 5, 10]
    assert r2["quantity"] == 3 and r2["type"] == "salida" and r2["reason"] == "venta"
    assert client.get(f"/products/{product.id}", headers=admin_headers).json()["stock"] == 10
    stock_invariant()


def test_movement_user_comes_from_token(client, move, operator_headers, admin_headers, product, db):
    operator_id = db.execute(text("SELECT id FROM users WHERE email='operator@example.com'")).scalar()
    r = move(operator_headers, product.id, "entrada", 1)
    assert r.json()["user_id"] == operator_id
    # Intentar suplantar a otro usuario desde el cuerpo se rechaza.
    forged = move(operator_headers, product.id, "entrada", 1, user_id=999)
    assert forged.status_code == 422
    assert db.execute(text("SELECT count(*) FROM stock_movements")).scalar() == 1


def test_created_at_is_set_and_increasing(move, admin_headers, product):
    first = move(admin_headers, product.id, "entrada", 1).json()["created_at"]
    second = move(admin_headers, product.id, "entrada", 1).json()["created_at"]
    assert first < second


def test_salida_without_enough_stock_is_409_and_changes_nothing(
    client, move, admin_headers, product, db, stock_invariant
):
    move(admin_headers, product.id, "entrada", 5)
    r = move(admin_headers, product.id, "salida", 6)
    assert r.status_code == 409
    assert r.json()["code"] == "insufficient_stock"
    assert db.execute(text("SELECT count(*) FROM stock_movements")).scalar() == 1
    assert client.get(f"/products/{product.id}", headers=admin_headers).json()["stock"] == 5
    stock_invariant()


def test_salida_of_exact_stock_leaves_zero(client, move, admin_headers, product):
    move(admin_headers, product.id, "entrada", 5)
    assert move(admin_headers, product.id, "salida", 5).status_code == 201
    assert client.get(f"/products/{product.id}", headers=admin_headers).json()["stock"] == 0
    assert move(admin_headers, product.id, "salida", 1).status_code == 409


def test_negative_ajuste_beyond_stock_is_409(move, admin_headers, product):
    move(admin_headers, product.id, "entrada", 2)
    r = move(admin_headers, product.id, "ajuste", -3)
    assert r.status_code == 409 and r.json()["code"] == "insufficient_stock"


def test_stock_cannot_exceed_integer_limit(move, admin_headers, product):
    assert move(admin_headers, product.id, "entrada", 2_147_483_647).status_code == 201
    r = move(admin_headers, product.id, "entrada", 1)
    assert r.status_code == 409 and r.json()["code"] == "stock_limit_exceeded"


# --- validaciones -----------------------------------------------------------


@pytest.mark.parametrize(
    "type_, quantity",
    [
        ("entrada", 0),
        ("entrada", -1),
        ("salida", 0),
        ("salida", -5),
        ("ajuste", 0),
        ("entrada", 1.5),
        ("entrada", "diez"),
        ("entrada", 2_147_483_648),
        ("ajuste", -2_147_483_648),
    ],
)
def test_invalid_quantities_are_422(move, admin_headers, product, db, type_, quantity):
    r = move(admin_headers, product.id, type_, quantity)
    assert r.status_code == 422
    assert r.json()["code"] == "validation_error"
    assert db.execute(text("SELECT count(*) FROM stock_movements")).scalar() == 0


@pytest.mark.parametrize("reason", ["", "   ", "x" * 256])
def test_invalid_reason_is_422(move, admin_headers, product, reason):
    assert move(admin_headers, product.id, "entrada", 1, reason).status_code == 422


def test_invalid_type_and_missing_fields_are_422(client, move, admin_headers, product):
    assert move(admin_headers, product.id, "transferencia", 1).status_code == 422
    assert client.post("/stock-movements", json={}, headers=admin_headers).status_code == 422
    assert client.post(
        "/stock-movements", json={"product_id": product.id, "type": "entrada", "quantity": 1},
        headers=admin_headers,
    ).status_code == 422


def test_unknown_product_is_404(move, admin_headers):
    r = move(admin_headers, 9999, "entrada", 1)
    assert r.status_code == 404 and r.json()["code"] == "not_found"


def test_inactive_product_is_409(move, admin_headers, make_product, db):
    inactive = make_product("OFF-1", is_active=False)
    r = move(admin_headers, inactive.id, "entrada", 1)
    assert r.status_code == 409
    assert r.json()["code"] == "inactive_product"
    assert db.execute(text("SELECT count(*) FROM stock_movements")).scalar() == 0


# --- listado ----------------------------------------------------------------


@pytest.fixture
def history(client, move, admin_headers, operator_headers, make_product):
    a, b = make_product("A-1"), make_product("B-1")
    move(admin_headers, a.id, "entrada", 10)       # 1
    move(admin_headers, b.id, "entrada", 8)        # 2
    move(operator_headers, a.id, "salida", 2)      # 3
    move(admin_headers, a.id, "ajuste", -1)        # 4
    move(operator_headers, b.id, "salida", 1)      # 5
    return a, b


def test_list_is_newest_first_and_paginated(client, admin_headers, history):
    r = client.get("/stock-movements", headers=admin_headers).json()
    assert r["total"] == 5 and r["limit"] == 20 and r["offset"] == 0
    assert [m["id"] for m in r["items"]] == [5, 4, 3, 2, 1]
    page = client.get("/stock-movements?limit=2&offset=1", headers=admin_headers).json()
    assert [m["id"] for m in page["items"]] == [4, 3]
    assert page["total"] == 5
    assert client.get("/stock-movements?limit=101", headers=admin_headers).status_code == 422
    assert client.get("/stock-movements?limit=0", headers=admin_headers).status_code == 422


def test_filter_by_product(client, admin_headers, history):
    a, b = history
    r = client.get(f"/stock-movements?product_id={a.id}", headers=admin_headers).json()
    assert r["total"] == 3 and {m["product_id"] for m in r["items"]} == {a.id}


def test_filter_by_type(client, admin_headers, history):
    r = client.get("/stock-movements?type=salida", headers=admin_headers).json()
    assert r["total"] == 2 and {m["type"] for m in r["items"]} == {"salida"}
    assert client.get("/stock-movements?type=otra", headers=admin_headers).status_code == 422


def test_filter_by_user(client, admin_headers, history, db):
    operator_id = db.execute(text("SELECT id FROM users WHERE email='operator@example.com'")).scalar()
    r = client.get(f"/stock-movements?user_id={operator_id}", headers=admin_headers).json()
    assert r["total"] == 2 and {m["user_id"] for m in r["items"]} == {operator_id}


def test_filter_by_date_range(client, admin_headers, history, db):
    db.rollback()
    # created_at es inmutable por trigger solo para UPDATE vía la app; se fijan fechas
    # distintas deshabilitando el trigger dentro de esta transacción de preparación.
    db.execute(text("ALTER TABLE stock_movements DISABLE TRIGGER trg_stock_movements_immutable"))
    for movement_id, day in [(1, "01"), (2, "02"), (3, "03"), (4, "04"), (5, "05")]:
        db.execute(
            text("UPDATE stock_movements SET created_at = :d WHERE id = :i"),
            {"d": f"2026-01-{day}T12:00:00+00:00", "i": movement_id},
        )
    db.execute(text("ALTER TABLE stock_movements ENABLE TRIGGER trg_stock_movements_immutable"))
    db.commit()

    def ids(**params):
        r = client.get("/stock-movements", params=params, headers=admin_headers).json()
        return sorted(m["id"] for m in r["items"])

    assert ids(date_from="2026-01-03T12:00:00Z") == [3, 4, 5]      # inclusivo
    assert ids(date_to="2026-01-02T12:00:00Z") == [1, 2]           # inclusivo
    assert ids(date_from="2026-01-02T00:00:00Z", date_to="2026-01-04T12:00:00Z") == [2, 3, 4]
    assert ids(date_from="2026-01-03T12:00:00") == [3, 4, 5]       # sin zona = UTC
    assert ids(date_from="2027-01-01T00:00:00Z") == []
    bad = client.get(
        "/stock-movements?date_from=2026-02-01T00:00:00Z&date_to=2026-01-01T00:00:00Z",
        headers=admin_headers,
    )
    assert bad.status_code == 422
    assert client.get("/stock-movements?date_from=ayer", headers=admin_headers).status_code == 422


def test_filters_combine(client, admin_headers, history):
    a, _ = history
    r = client.get(f"/stock-movements?product_id={a.id}&type=salida", headers=admin_headers).json()
    assert r["total"] == 1


# --- inmutabilidad ----------------------------------------------------------


def test_movements_have_no_update_or_delete_endpoints(client, admin_headers, history, db):
    before = db.execute(text("SELECT id, quantity, reason, stock_after FROM stock_movements ORDER BY id")).all()
    for method in ("patch", "put", "delete"):
        r = getattr(client, method)("/stock-movements/1", headers=admin_headers)
        assert r.status_code in (404, 405)
        r = getattr(client, method)("/stock-movements", headers=admin_headers)
        assert r.status_code in (404, 405)
    after = db.execute(text("SELECT id, quantity, reason, stock_after FROM stock_movements ORDER BY id")).all()
    assert before == after


def test_database_rejects_update_and_delete_of_movements(db, history):
    from sqlalchemy.exc import IntegrityError

    with pytest.raises(IntegrityError, match="append-only"):
        db.execute(text("UPDATE stock_movements SET quantity = 999 WHERE id = 1"))
    db.rollback()
    with pytest.raises(IntegrityError, match="append-only"):
        db.execute(text("DELETE FROM stock_movements WHERE id = 1"))
    db.rollback()
    assert db.execute(text("SELECT count(*) FROM stock_movements")).scalar() == 5


def test_database_check_rejects_negative_stock_after_the_app(db, make_product):
    """Red de seguridad: aunque se saltara la app, la base rechaza stock negativo."""
    from sqlalchemy.exc import IntegrityError

    product = make_product("RED-1", stock=1)
    with pytest.raises(IntegrityError, match="ck_products_stock_non_negative"):
        db.execute(text("UPDATE products SET stock = stock - 2 WHERE id = :p"), {"p": product.id})
    db.rollback()
