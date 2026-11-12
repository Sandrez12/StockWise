import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database import engine, get_db

pytestmark = pytest.mark.integration


def test_get_db_yields_working_session(test_database):
    gen = get_db()
    db = next(gen)
    try:
        assert isinstance(db, Session)
        assert db.execute(text("SELECT 1")).scalar() == 1
        assert db.execute(text("SELECT current_database()")).scalar() == test_database
    finally:
        gen.close()


def test_get_db_releases_connection(test_database):
    gen = get_db()
    db = next(gen)
    db.execute(text("SELECT 1"))
    assert engine.pool.checkedout() == 1

    gen.close()

    assert not db.in_transaction()
    assert engine.pool.checkedout() == 0


def test_get_db_works_as_fastapi_dependency(test_database):
    app = FastAPI()

    @app.get("/db")
    def current_db(db: Session = Depends(get_db)):
        return {"database": db.execute(text("SELECT current_database()")).scalar()}

    response = TestClient(app).get("/db")
    assert response.status_code == 200
    assert response.json() == {"database": test_database}
