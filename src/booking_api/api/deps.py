from collections.abc import Generator

from sqlalchemy.orm import Session

from booking_api.application.booking_service import BookingService
from booking_api.application.resource_service import ResourceService
from booking_api.infra.db import SessionLocal
from booking_api.infra.repositories import SqlAlchemyBookingRepository, SqlAlchemyResourceRepository


def get_db() -> Generator[Session, None, None]:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def get_resource_service(session: Session) -> ResourceService:
    return ResourceService(SqlAlchemyResourceRepository(session))


def get_booking_service(session: Session) -> BookingService:
    return BookingService(
        SqlAlchemyResourceRepository(session),
        SqlAlchemyBookingRepository(session),
    )
