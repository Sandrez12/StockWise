import pytest

pytestmark = pytest.mark.integration


def test_requires_authentication(client):
    assert client.get("/categories").status_code == 401
    assert client.post("/categories", json={"name": "X"}).status_code == 401


def test_operator_can_read_but_not_write(client, operator_headers, make_category):
    cat = make_category("Bebidas")
    assert client.get("/categories", headers=operator_headers).status_code == 200
    assert client.get(f"/categories/{cat.id}", headers=operator_headers).status_code == 200
    h = operator_headers
    assert client.post("/categories", json={"name": "Nueva"}, headers=h).status_code == 403
    assert client.patch(f"/categories/{cat.id}", json={"name": "Z"}, headers=h).status_code == 403
    assert client.delete(f"/categories/{cat.id}", headers=h).status_code == 403


def test_admin_creates_category(client, admin_headers):
    r = client.post(
        "/categories", json={"name": "  Bebidas ", "description": "Líquidos"}, headers=admin_headers
    )
    assert r.status_code == 201
    body = r.json()
    assert body["name"] == "Bebidas" and body["is_active"] is True and body["description"] == "Líquidos"


def test_duplicate_name_is_409_case_insensitive(client, admin_headers):
    client.post("/categories", json={"name": "Bebidas"}, headers=admin_headers)
    r = client.post("/categories", json={"name": "bebidas"}, headers=admin_headers)
    assert r.status_code == 409
    assert r.json()["code"] == "conflict"


@pytest.mark.parametrize(
    "payload",
    [{}, {"name": ""}, {"name": "   "}, {"name": "x" * 101}, {"name": "A", "extra": 1}],
)
def test_create_validation(client, admin_headers, payload):
    r = client.post("/categories", json=payload, headers=admin_headers)
    assert r.status_code == 422
    assert r.json()["code"] == "validation_error"


def test_list_paginates_with_total_and_cap(client, admin_headers, make_category):
    for i in range(5):
        make_category(f"Cat {i}")
    r = client.get("/categories?limit=2&offset=2", headers=admin_headers).json()
    assert r["total"] == 5 and r["limit"] == 2 and r["offset"] == 2
    assert [c["name"] for c in r["items"]] == ["Cat 2", "Cat 3"]
    assert client.get("/categories?limit=101", headers=admin_headers).status_code == 422
    assert client.get("/categories?limit=0", headers=admin_headers).status_code == 422
    assert client.get("/categories?offset=-1", headers=admin_headers).status_code == 422


def test_search_by_name_and_wildcards_are_literal(client, admin_headers, make_category):
    make_category("Bebidas")
    make_category("Limpieza")
    make_category("100% algodón")
    names = lambda q: [c["name"] for c in client.get("/categories", params={"q": q}, headers=admin_headers).json()["items"]]
    assert names("beb") == ["Bebidas"]
    assert names("%") == ["100% algodón"]
    assert names("_") == []


def test_inactive_hidden_unless_admin_asks(client, admin_headers, operator_headers, make_category):
    make_category("Activa")
    inactive = make_category("Vieja", is_active=False)
    assert client.get("/categories", headers=admin_headers).json()["total"] == 1
    assert client.get("/categories?include_inactive=true", headers=admin_headers).json()["total"] == 2
    assert client.get("/categories?include_inactive=true", headers=operator_headers).status_code == 403
    assert client.get(f"/categories/{inactive.id}", headers=operator_headers).status_code == 404
    assert client.get(f"/categories/{inactive.id}", headers=admin_headers).status_code == 200


def test_update_category(client, admin_headers, make_category):
    cat = make_category("Bebidas")
    other = make_category("Limpieza")
    ok = client.patch(f"/categories/{cat.id}", json={"name": "Líquidos"}, headers=admin_headers)
    assert ok.status_code == 200 and ok.json()["name"] == "Líquidos"
    clash = client.patch(f"/categories/{cat.id}", json={"name": "limpieza"}, headers=admin_headers)
    assert clash.status_code == 409
    same = client.patch(f"/categories/{other.id}", json={"name": "LIMPIEZA"}, headers=admin_headers)
    assert same.status_code == 200
    assert client.patch("/categories/9999", json={"name": "X"}, headers=admin_headers).status_code == 404


def test_delete_is_soft_and_idempotent(client, admin_headers, make_category, db):
    cat = make_category("Bebidas")
    assert client.delete(f"/categories/{cat.id}", headers=admin_headers).status_code == 204
    assert client.delete(f"/categories/{cat.id}", headers=admin_headers).status_code == 204
    db.refresh(cat)
    assert cat.is_active is False
    assert client.patch(f"/categories/{cat.id}", json={"is_active": True}, headers=admin_headers).json()["is_active"] is True
    assert client.delete("/categories/9999", headers=admin_headers).status_code == 404


def test_cannot_deactivate_category_with_active_products(client, admin_headers, make_category, make_product):
    cat = make_category("Bebidas")
    product = make_product("A-1", category=cat)
    assert client.delete(f"/categories/{cat.id}", headers=admin_headers).status_code == 409
    r = client.patch(f"/categories/{cat.id}", json={"is_active": False}, headers=admin_headers)
    assert r.status_code == 409
    client.delete(f"/products/{product.id}", headers=admin_headers)
    assert client.delete(f"/categories/{cat.id}", headers=admin_headers).status_code == 204
