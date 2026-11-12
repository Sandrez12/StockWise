import pytest

pytestmark = pytest.mark.integration


def _payload(category_id, **overrides):
    return {"sku": "AGU-001", "name": "Agua 500 ml", "price": "1.50", "category_id": category_id, **overrides}


def test_requires_authentication(client):
    assert client.get("/products").status_code == 401
    assert client.post("/products", json={}).status_code == 401


def test_operator_can_read_but_not_write(client, operator_headers, make_product):
    product = make_product()
    h = operator_headers
    assert client.get("/products", headers=h).status_code == 200
    assert client.get(f"/products/{product.id}", headers=h).status_code == 200
    assert client.post("/products", json=_payload(product.category_id), headers=h).status_code == 403
    assert client.patch(f"/products/{product.id}", json={"name": "X"}, headers=h).status_code == 403
    assert client.delete(f"/products/{product.id}", headers=h).status_code == 403


def test_admin_creates_product_with_zero_stock_and_normalized_sku(client, admin_headers, make_category):
    cat = make_category()
    r = client.post("/products", json=_payload(cat.id, sku=" agu-001 "), headers=admin_headers)
    assert r.status_code == 201
    body = r.json()
    assert body["sku"] == "AGU-001"
    assert body["stock"] == 0
    assert body["price"] == "1.50"
    assert body["is_active"] is True


def test_stock_cannot_be_set_on_create(client, admin_headers, make_category):
    cat = make_category()
    r = client.post("/products", json=_payload(cat.id, stock=50), headers=admin_headers)
    assert r.status_code == 422


def test_stock_cannot_be_edited_by_patch(client, admin_headers, make_product, db):
    product = make_product(stock=7)
    r = client.patch(f"/products/{product.id}", json={"stock": 999}, headers=admin_headers)
    assert r.status_code == 422
    assert any(e["field"].endswith("stock") for e in r.json()["errors"])
    db.refresh(product)
    assert product.stock == 7
    mixed = client.patch(f"/products/{product.id}", json={"name": "Nuevo", "stock": 1}, headers=admin_headers)
    assert mixed.status_code == 422
    db.refresh(product)
    assert product.name != "Nuevo" and product.stock == 7


def test_duplicate_sku_is_409(client, admin_headers, make_category):
    cat = make_category()
    assert client.post("/products", json=_payload(cat.id), headers=admin_headers).status_code == 201
    r = client.post("/products", json=_payload(cat.id, sku="agu-001"), headers=admin_headers)
    assert r.status_code == 409
    assert r.json() == {"detail": "Ya existe un producto con ese SKU", "code": "conflict"}


def test_patch_to_existing_sku_is_409(client, admin_headers, make_product):
    a = make_product("A-1")
    make_product("B-1")
    r = client.patch(f"/products/{a.id}", json={"sku": "b-1"}, headers=admin_headers)
    assert r.status_code == 409
    keep = client.patch(f"/products/{a.id}", json={"sku": "a-1", "name": "Mismo SKU"}, headers=admin_headers)
    assert keep.status_code == 200


@pytest.mark.parametrize(
    "override",
    [
        {"sku": ""},
        {"sku": "con espacio"},
        {"sku": "ñandú"},
        {"name": "  "},
        {"price": "-1"},
        {"price": "1.505"},
        {"price": "abc"},
        {"price": "10000000000.00"},
    ],
)
def test_create_validation(client, admin_headers, make_category, override):
    cat = make_category()
    r = client.post("/products", json=_payload(cat.id, **override), headers=admin_headers)
    assert r.status_code == 422
    assert r.json()["code"] == "validation_error"


def test_missing_fields_are_422(client, admin_headers):
    r = client.post("/products", json={}, headers=admin_headers)
    assert r.status_code == 422
    assert {e["field"] for e in r.json()["errors"]} >= {"body.sku", "body.name", "body.price", "body.category_id"}


def test_category_must_exist_and_be_active(client, admin_headers, make_category):
    assert client.post("/products", json=_payload(9999), headers=admin_headers).status_code == 422
    inactive = make_category("Vieja", is_active=False)
    assert client.post("/products", json=_payload(inactive.id), headers=admin_headers).status_code == 422


def test_patch_updates_fields_and_moves_category(client, admin_headers, make_product, make_category):
    product = make_product("A-1", price="2.00")
    new_cat = make_category("Otra")
    r = client.patch(
        f"/products/{product.id}",
        json={"name": "Renombrado", "price": "3.25", "category_id": new_cat.id, "description": "Nueva"},
        headers=admin_headers,
    )
    assert r.status_code == 200
    body = r.json()
    assert (body["name"], body["price"], body["category_id"], body["description"]) == ("Renombrado", "3.25", new_cat.id, "Nueva")
    bad = client.patch(f"/products/{product.id}", json={"category_id": 9999}, headers=admin_headers)
    assert bad.status_code == 422
    assert client.patch("/products/9999", json={"name": "X"}, headers=admin_headers).status_code == 404


def test_patch_null_for_required_field_does_not_change_it(client, admin_headers, make_product):
    product = make_product("A-1", name="Agua")
    r = client.patch(f"/products/{product.id}", json={"name": None}, headers=admin_headers)
    assert r.status_code == 200 and r.json()["name"] == "Agua"


def test_delete_is_soft_and_hides_from_operator(client, admin_headers, operator_headers, make_product, db):
    product = make_product("A-1", stock=3)
    assert client.delete(f"/products/{product.id}", headers=admin_headers).status_code == 204
    assert client.delete(f"/products/{product.id}", headers=admin_headers).status_code == 204
    db.refresh(product)
    assert product.is_active is False and product.stock == 3
    assert client.get("/products", headers=admin_headers).json()["total"] == 0
    assert client.get("/products?include_inactive=true", headers=admin_headers).json()["total"] == 1
    assert client.get(f"/products/{product.id}", headers=operator_headers).status_code == 404
    assert client.get(f"/products/{product.id}", headers=admin_headers).status_code == 200
    assert client.get("/products?include_inactive=true", headers=operator_headers).status_code == 403
    restored = client.patch(f"/products/{product.id}", json={"is_active": True}, headers=admin_headers)
    assert restored.json()["is_active"] is True
    assert client.delete("/products/9999", headers=admin_headers).status_code == 404


def test_pagination(client, admin_headers, make_product, make_category):
    cat = make_category()
    for i in range(1, 8):
        make_product(f"P-{i}", name=f"Prod {i}", category=cat)
    page = client.get("/products?limit=3&offset=3", headers=admin_headers).json()
    assert page["total"] == 7 and page["limit"] == 3 and page["offset"] == 3
    assert [p["sku"] for p in page["items"]] == ["P-4", "P-5", "P-6"]
    last = client.get("/products?limit=3&offset=6", headers=admin_headers).json()
    assert len(last["items"]) == 1
    assert client.get("/products?limit=500", headers=admin_headers).status_code == 422
    assert client.get("/products?limit=0", headers=admin_headers).status_code == 422
    default = client.get("/products", headers=admin_headers).json()
    assert default["limit"] == 20


def test_search_by_name_or_sku_case_insensitive(client, admin_headers, make_product, make_category):
    cat = make_category()
    make_product("AGU-001", name="Agua mineral", category=cat)
    make_product("JUG-002", name="Jugo de naranja", category=cat)
    make_product("COD_50%", name="Código raro", category=cat)

    def skus(q):
        r = client.get("/products", params={"q": q}, headers=admin_headers).json()
        return sorted(p["sku"] for p in r["items"])

    assert skus("agua") == ["AGU-001"]
    assert skus("jug-0") == ["JUG-002"]
    assert skus("NARANJA") == ["JUG-002"]
    assert skus("%") == ["COD_50%"]
    assert skus("_") == ["COD_50%"]
    assert skus("zzz") == []


def test_filter_by_category(client, admin_headers, make_product, make_category):
    a, b = make_category("A"), make_category("B")
    make_product("A-1", category=a)
    make_product("A-2", category=a)
    make_product("B-1", category=b)
    r = client.get(f"/products?category_id={a.id}", headers=admin_headers).json()
    assert r["total"] == 2
    assert {p["category_id"] for p in r["items"]} == {a.id}


def test_filter_low_stock(client, admin_headers, make_product, make_category):
    cat = make_category()
    # (sku, stock, min_stock): bajo cuando stock <= min_stock
    rows = [("S-0", 0, 0), ("S-5", 5, 5), ("S-6", 6, 5), ("S-3", 3, 10), ("S-50", 50, 10)]
    for sku, stock, min_stock in rows:
        make_product(sku, stock=stock, min_stock=min_stock, category=cat)

    def skus(**params):
        r = client.get("/products", params=params, headers=admin_headers).json()
        return sorted(p["sku"] for p in r["items"])

    assert skus(low_stock="true") == ["S-0", "S-3", "S-5"]
    assert len(skus()) == 5
    assert len(skus(low_stock="false")) == 5


def test_threshold_query_param_no_longer_exists(client, admin_headers, make_product):
    make_product("S-1", stock=1, min_stock=0)
    r = client.get("/products?low_stock=true&threshold=100", headers=admin_headers)
    assert r.status_code == 200
    assert r.json()["total"] == 0  # el parámetro se ignora; manda min_stock


def test_min_stock_defaults_to_zero_and_is_editable(client, admin_headers, make_category):
    cat = make_category()
    created = client.post(
        "/products",
        json={"sku": "M-1", "name": "Con umbral", "price": "1.00", "category_id": cat.id},
        headers=admin_headers,
    ).json()
    assert created["min_stock"] == 0
    r = client.patch(f"/products/{created['id']}", json={"min_stock": 8}, headers=admin_headers)
    assert r.status_code == 200 and r.json()["min_stock"] == 8
    with_value = client.post(
        "/products",
        json={"sku": "M-2", "name": "Otro", "price": "1.00", "category_id": cat.id, "min_stock": 4},
        headers=admin_headers,
    )
    assert with_value.json()["min_stock"] == 4


def test_min_stock_validation(client, admin_headers, make_product):
    product = make_product("M-1")
    for bad in (-1, "abc", 2_147_483_648):
        r = client.patch(f"/products/{product.id}", json={"min_stock": bad}, headers=admin_headers)
        assert r.status_code == 422


def test_filters_combine_with_pagination_total(client, admin_headers, make_product, make_category):
    cat = make_category()
    for i in range(6):
        make_product(f"L-{i}", name="Lote", stock=i, min_stock=3, category=cat)
    r = client.get("/products?q=lote&low_stock=true&limit=2", headers=admin_headers).json()
    assert r["total"] == 4 and len(r["items"]) == 2
