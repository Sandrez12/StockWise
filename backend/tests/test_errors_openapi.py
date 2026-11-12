from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_unknown_route_uses_standard_error_format():
    r = client.get("/no-existe")
    assert r.status_code == 404
    assert r.json() == {"detail": "Not Found", "code": "not_found"}


def test_wrong_method_uses_standard_error_format():
    r = client.delete("/")
    assert r.status_code == 405
    assert r.json()["code"] == "method_not_allowed"


def test_unauthenticated_error_keeps_www_authenticate_header():
    r = client.get("/auth/me")
    assert r.status_code == 401
    assert r.json() == {"detail": "Not authenticated", "code": "unauthorized"}
    assert r.headers["www-authenticate"] == "Bearer"


def test_validation_error_lists_fields_without_echoing_input():
    r = client.post(
        "/auth/login", data={"username": "a@example.com"}
    )
    assert r.status_code == 422
    body = r.json()
    assert body["code"] == "validation_error"
    assert body["errors"] == [{"field": "body.password", "message": "Field required"}]


def test_validation_error_never_echoes_submitted_values():
    # Sin autenticación esto sería 401; se comprueba el manejador con una ruta pública.
    r = client.post("/auth/login", data={"password": "secreto-que-no-debe-salir"})
    assert r.status_code == 422
    assert "secreto-que-no-debe-salir" not in r.text


def test_openapi_documents_tags_and_descriptions():
    spec = client.get("/openapi.json").json()
    tag_names = {t["name"] for t in spec["tags"]}
    assert {"Categorías", "Productos", "Usuarios", "Autenticación"} <= tag_names
    for path, methods in spec["paths"].items():
        for method, op in methods.items():
            assert op.get("tags"), f"{method} {path} sin etiqueta"
            assert op.get("summary"), f"{method} {path} sin resumen"


def test_openapi_exposes_error_schema_and_no_stock_in_product_update():
    spec = client.get("/openapi.json").json()
    schemas = spec["components"]["schemas"]
    assert "ErrorResponse" in schemas
    assert "stock" not in schemas["ProductUpdate"]["properties"]
    assert "stock" not in schemas["ProductCreate"]["properties"]
    assert "stock" in schemas["ProductRead"]["properties"]
