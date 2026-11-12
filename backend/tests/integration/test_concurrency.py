"""Concurrencia real: hilos, conexiones separadas y la base PostgreSQL de pruebas, sin mocks.

Cada hilo usa su propio TestClient; cada petición abre su propia sesión (conexión
del pool), así que las operaciones compiten de verdad por la fila del producto.
"""

import threading
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.main import app

pytestmark = pytest.mark.integration


def run_concurrently(jobs):
    """Ejecuta los jobs a la vez (barrera) y devuelve sus resultados en orden."""
    barrier = threading.Barrier(len(jobs))

    def wrap(job):
        client = TestClient(app)
        barrier.wait(timeout=30)
        return job(client)

    with ThreadPoolExecutor(max_workers=len(jobs)) as pool:
        futures = [pool.submit(wrap, job) for job in jobs]
        return [f.result(timeout=120) for f in futures]


def post(headers, product_id, type_, quantity):
    def job(client):
        return client.post(
            "/stock-movements",
            json={"product_id": product_id, "type": type_, "quantity": quantity, "reason": "concurrencia"},
            headers=headers,
        )

    return job


@pytest.fixture
def stocked(make_product, move, admin_headers):
    """Producto creado con stock 0 y llevado a 10 con un movimiento (invariante válido)."""

    def _make(initial=10):
        product = make_product("CON-1", stock=0)
        assert move(admin_headers, product.id, "entrada", initial).status_code == 201
        return product

    return _make


def test_20_concurrent_salidas_on_stock_10_succeed_exactly_10_times(
    db, stocked, operator_headers, stock_invariant
):
    product = stocked(10)
    responses = run_concurrently([post(operator_headers, product.id, "salida", 1) for _ in range(20)])

    codes = Counter(r.status_code for r in responses)
    assert codes == {201: 10, 409: 10}, codes
    assert {r.json()["code"] for r in responses if r.status_code == 409} == {"insufficient_stock"}

    db.rollback()
    assert db.execute(text("SELECT stock FROM products WHERE id = :p"), {"p": product.id}).scalar() == 0
    salidas = db.execute(
        text("SELECT count(*) FROM stock_movements WHERE product_id = :p AND type = 'salida'"),
        {"p": product.id},
    ).scalar()
    assert salidas == 10
    stock_invariant()


def test_stock_after_forms_a_consistent_chain_under_concurrency(db, stocked, operator_headers):
    product = stocked(10)
    run_concurrently([post(operator_headers, product.id, "salida", 1) for _ in range(20)])
    db.rollback()
    rows = db.execute(
        text("SELECT type, quantity, stock_after, created_at FROM stock_movements "
             "WHERE product_id = :p ORDER BY id"),
        {"p": product.id},
    ).all()
    running = 0
    for type_, quantity, stock_after, _ in rows:
        running += -quantity if type_ == "salida" else quantity
        assert stock_after == running
        assert stock_after >= 0
    created = [r[3] for r in rows]
    assert created == sorted(created)  # created_at monótona por producto


def test_mixed_concurrent_entradas_and_salidas_keep_the_invariant(
    db, stocked, admin_headers, operator_headers, stock_invariant
):
    product = stocked(20)
    jobs = []
    for i in range(30):
        quantity = (i % 5) + 1
        headers = operator_headers if i % 2 else admin_headers
        jobs.append(post(headers, product.id, "entrada" if i % 3 else "salida", quantity))
    responses = run_concurrently(jobs)

    assert {r.status_code for r in responses} <= {201, 409}
    db.rollback()
    final_stock = db.execute(text("SELECT stock FROM products WHERE id = :p"), {"p": product.id}).scalar()
    signed_sum = db.execute(
        text("SELECT SUM(CASE WHEN type = 'salida' THEN -quantity ELSE quantity END) "
             "FROM stock_movements WHERE product_id = :p"),
        {"p": product.id},
    ).scalar()
    movements = db.execute(
        text("SELECT count(*) FROM stock_movements WHERE product_id = :p"), {"p": product.id}
    ).scalar()
    assert final_stock == signed_sum
    assert final_stock >= 0
    assert movements == 1 + sum(1 for r in responses if r.status_code == 201)  # 1 = entrada inicial
    stock_invariant()


def test_concurrent_salidas_and_ajustes_never_go_negative(
    db, stocked, admin_headers, operator_headers, stock_invariant
):
    product = stocked(10)
    jobs = []
    for i in range(24):
        if i % 4 == 0:
            jobs.append(post(admin_headers, product.id, "ajuste", -3))
        elif i % 4 == 1:
            jobs.append(post(admin_headers, product.id, "ajuste", 2))
        else:
            jobs.append(post(operator_headers, product.id, "salida", 2))
    responses = run_concurrently(jobs)
    assert {r.status_code for r in responses} <= {201, 409}
    db.rollback()
    assert db.execute(text("SELECT stock FROM products WHERE id = :p"), {"p": product.id}).scalar() >= 0
    stock_invariant()


def test_concurrent_stock_counts_serialize(db, stocked, admin_headers, stock_invariant):
    product = stocked(10)

    def count_job(counted):
        def job(client):
            return client.post(
                f"/products/{product.id}/stock-count", json={"counted": counted}, headers=admin_headers
            )

        return job

    responses = run_concurrently([count_job(n) for n in (3, 7, 12, 0, 5, 9)])
    assert all(r.status_code == 200 for r in responses)
    db.rollback()
    final = db.execute(text("SELECT stock FROM products WHERE id = :p"), {"p": product.id}).scalar()
    last_after = db.execute(
        text("SELECT stock_after FROM stock_movements WHERE product_id = :p ORDER BY id DESC LIMIT 1"),
        {"p": product.id},
    ).scalar()
    assert final == last_after
    stock_invariant()


def test_concurrency_on_different_products_does_not_interfere(
    db, make_product, move, admin_headers, operator_headers, stock_invariant
):
    products = [make_product(f"IND-{i}", stock=0) for i in range(4)]
    for p in products:
        move(admin_headers, p.id, "entrada", 5)
    jobs = [post(operator_headers, p.id, "salida", 1) for p in products for _ in range(8)]
    responses = run_concurrently(jobs)
    assert Counter(r.status_code for r in responses) == {201: 20, 409: 12}
    db.rollback()
    stocks = db.execute(text("SELECT stock FROM products ORDER BY id")).scalars().all()
    assert stocks == [0, 0, 0, 0]
    stock_invariant()
