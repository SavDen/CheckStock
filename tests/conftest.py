"""Integration tests run only against a separate PostgreSQL database ending in _test."""

import os

import psycopg
import pytest
from sqlalchemy.engine import make_url

url = os.getenv(
    "TEST_DATABASE_URL", "postgresql+psycopg://checkstock:checkstock@localhost:5432/checkstock_test"
)
parsed = make_url(url)
if parsed.get_backend_name() != "postgresql" or not parsed.database.endswith("_test"):
    raise RuntimeError("TEST_DATABASE_URL must point to a separate PostgreSQL database ending in _test")
os.environ["DATABASE_URL"] = url
os.environ["SEED_DEMO"] = "false"

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.db import SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.seed import seed  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def database():
    admin = parsed.set(database="postgres", drivername="postgresql").render_as_string(hide_password=False)
    with psycopg.connect(admin, autocommit=True) as connection:
        exists = connection.execute(
            "SELECT 1 FROM pg_database WHERE datname=%s", (parsed.database,)
        ).fetchone()
        if not exists:
            from psycopg import sql

            connection.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(parsed.database)))
    from alembic import command
    from alembic.config import Config

    command.upgrade(Config("alembic.ini"), "head")
    yield
    engine.dispose()


@pytest.fixture(autouse=True)
def reset(database):
    with SessionLocal.begin() as db:
        db.execute(
            text(
                "TRUNCATE events, idempotency, movements, stocks, products, warehouses RESTART IDENTITY CASCADE"
            )
        )
    seed()


@pytest.fixture
def client():
    with TestClient(app) as client:
        yield client
