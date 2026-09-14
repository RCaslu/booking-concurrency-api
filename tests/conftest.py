import os
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

from booking_api.api.deps import get_db
from booking_api.api.main import create_app
from booking_api.infra.bootstrap import drop_db, init_db
from booking_api.infra.db import build_engine

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+psycopg://booking:booking@localhost:5433/booking_test"
)


@pytest.fixture(scope="session")
def engine():
    eng = build_engine(TEST_DATABASE_URL, pool_size=30, max_overflow=10)
    init_db(eng)
    yield eng
    drop_db(eng)
    eng.dispose()


@pytest.fixture(scope="session")
def session_factory(engine):
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


@pytest.fixture
def _clean_db(engine):
    """Only pulled in by fixtures that actually touch the database (db_session,
    client) — keeps tests/unit/* from ever connecting to Postgres at all."""
    yield
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE TABLE bookings, resources RESTART IDENTITY CASCADE"))


@pytest.fixture
def db_session(session_factory, _clean_db):
    session = session_factory()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client(engine, session_factory, _clean_db):
    app = create_app(engine=engine)

    def override_get_db():
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def resource(client):
    res = client.post("/resources", json={"name": "Sala A", "capacity": 8, "location": "1º andar"})
    assert res.status_code == 201, res.text
    return res.json()


@pytest.fixture
def resource_id(resource):
    return resource["id"]


class TimeSlot:
    def __init__(self, start: datetime, end: datetime) -> None:
        self.start = start
        self.end = end


@pytest.fixture
def future_slot() -> TimeSlot:
    start = datetime.now(timezone.utc) + timedelta(days=1)
    end = start + timedelta(hours=1)
    return TimeSlot(start, end)
