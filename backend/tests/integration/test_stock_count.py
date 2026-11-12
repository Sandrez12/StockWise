import pytest
from sqlalchemy import text

pytestmark = pytest.mark.integration


@pytest.fixture
def product(make_product):
    return make_product("CNT-1", stock=0)


def count(client, headers, product_id, counted, **extra):
    return client.post(
        f"/products/{product_id}/stock-count", json={"counted": counted} | extra, headers=headers
    )


def test_operator_cannot_count(client, operator_headers, product):
    assert count(client, operator_headers, product.id, 5).status_code == 403


def test_count_higher_than_stock_registers_positive_adjustment(
    client, move, admin_headers, product, stock_invariant
):
    move(admin_headers, product.id, "entrada", 10)
    r = count(client, admin_headers, product.id, 13, note="Inventario de fin de mes")
    assert r.status_code == 200
    body = r.json()
    assert (body["previous_stock"], body["counted"], body["difference"], body["changed"]) == (10, 13, 3, True)
    movement = body["movement"]
    assert movement["type"] == "ajuste" and movement["quantity"] == 3 and movement["stock_after"] == 13
    assert movement["reason"] == "Conteo físico: Inventario de fin de mes"
    assert client.get(f"/products/{product.id}", headers=admin_headers).json()["stock"] == 13
    stock_invariant()


def test_count_lower_than_stock_registers_negative_adjustment(
    client, move, admin_headers, product, stock_invariant
):
    move(admin_headers, product.id, "entrada", 10)
    body = count(client, admin_headers, product.id, 4).json()
    assert body["difference"] == -6 and body["movement"]["quantity"] == -6
    assert body["movement"]["reason"] == "Conteo físico"
    assert body["movement"]["stock_after"] == 4
    stock_invariant()


def test_count_to_zero(client, move, admin_headers, product):
    move(admin_headers, product.id, "entrada", 3)
    body = count(client, admin_headers, product.id, 0).json()
    assert body["difference"] == -3 and client.get(f"/products/{product.id}", headers=admin_headers).json()["stock"] == 0


def test_zero_difference_creates_no_movement(client, move, admin_headers, product, db):
    move(admin_headers, product.id, "entrada", 7)
    r = count(client, admin_headers, product.id, 7)
    assert r.status_code == 200
    body = r.json()
    assert body["changed"] is False and body["difference"] == 0 and body["movement"] is None
    assert "no se creó" in body["message"]
    assert db.execute(text("SELECT count(*) FROM stock_movements")).scalar() == 1


@pytest.mark.parametrize("payload", [{}, {"counted": -1}, {"counted": "x"}, {"counted": 1.5}, {"counted": 2_147_483_648}, {"counted": 1, "user_id": 1}])
def test_invalid_count_is_422(client, admin_headers, product, payload):
    r = client.post(f"/products/{product.id}/stock-count", json=payload, headers=admin_headers)
    assert r.status_code == 422


def test_count_unknown_and_inactive_products(client, admin_headers, make_product):
    assert count(client, admin_headers, 9999, 1).status_code == 404
    inactive = make_product("OFF-2", is_active=False)
    r = count(client, admin_headers, inactive.id, 1)
    assert r.status_code == 409 and r.json()["code"] == "inactive_product"


def test_count_movement_is_attributed_to_the_admin_in_the_token(client, admin_headers, product, move, db):
    move(admin_headers, product.id, "entrada", 1)
    count(client, admin_headers, product.id, 5)
    admin_id = db.execute(text("SELECT id FROM users WHERE email='admin@example.com'")).scalar()
    assert db.execute(text("SELECT user_id FROM stock_movements WHERE type='ajuste'")).scalar() == admin_id
