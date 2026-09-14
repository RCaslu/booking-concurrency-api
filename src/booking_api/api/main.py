from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.engine import Engine

from booking_api.api.routers import bookings, resources
from booking_api.domain.exceptions import (
    BookingAlreadyCancelledError,
    BookingAlreadyStartedError,
    BookingNotFoundError,
    BookingQuotaExceededError,
    DomainError,
    InvalidTimeWindowError,
    OverlappingBookingError,
    ResourceNotFoundError,
)
from booking_api.infra.bootstrap import init_db

_STATUS_BY_EXCEPTION: dict[type[DomainError], int] = {
    ResourceNotFoundError: status.HTTP_404_NOT_FOUND,
    BookingNotFoundError: status.HTTP_404_NOT_FOUND,
    InvalidTimeWindowError: status.HTTP_422_UNPROCESSABLE_CONTENT,
    OverlappingBookingError: status.HTTP_409_CONFLICT,
    BookingQuotaExceededError: status.HTTP_409_CONFLICT,
    BookingAlreadyStartedError: status.HTTP_409_CONFLICT,
    BookingAlreadyCancelledError: status.HTTP_409_CONFLICT,
}


def create_app(engine: Engine | None = None) -> FastAPI:
    if engine is None:
        from booking_api.infra.db import engine as default_engine

        engine = default_engine

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        init_db(engine)
        yield

    app = FastAPI(title="Booking Concurrency API", lifespan=lifespan)

    @app.exception_handler(DomainError)
    def handle_domain_error(request: Request, exc: DomainError) -> JSONResponse:
        status_code = _STATUS_BY_EXCEPTION.get(type(exc), status.HTTP_400_BAD_REQUEST)
        return JSONResponse(
            status_code=status_code,
            content={"error_code": exc.error_code, "message": str(exc), "details": None},
        )

    app.include_router(resources.router)
    app.include_router(bookings.router)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
