from sqlalchemy import create_engine, pool

from alembic import context
from app import models  # noqa: F401
from app.db import DATABASE_URL, Base


def run_migrations():
    engine = create_engine(DATABASE_URL, poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=Base.metadata)
        with context.begin_transaction():
            context.run_migrations()


run_migrations()
