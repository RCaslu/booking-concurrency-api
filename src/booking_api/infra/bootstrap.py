from sqlalchemy import text
from sqlalchemy.engine import Engine

from booking_api.infra.db import Base
from booking_api.infra.models import BookingModel, ResourceModel  # noqa: F401 (registers mappers)


def init_db(engine: Engine) -> None:
    """Enables btree_gist (required by the EXCLUDE constraint) and creates tables."""
    with engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS btree_gist"))
        Base.metadata.create_all(conn)


def drop_db(engine: Engine) -> None:
    with engine.begin() as conn:
        Base.metadata.drop_all(conn)
