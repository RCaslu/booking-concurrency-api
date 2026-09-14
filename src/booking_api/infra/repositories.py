from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from booking_api.domain.entities import Booking, BookingStatus, Resource
from booking_api.domain.exceptions import BookingAlreadyCancelledError, OverlappingBookingError
from booking_api.infra.models import BookingModel, ResourceModel


def _to_resource(model: ResourceModel) -> Resource:
    return Resource(
        id=model.id,
        name=model.name,
        capacity=model.capacity,
        location=model.location,
        created_at=model.created_at,
    )


def _to_booking(model: BookingModel) -> Booking:
    return Booking(
        id=model.id,
        resource_id=model.resource_id,
        requester_email=model.requester_email,
        start_time=model.start_time,
        end_time=model.end_time,
        status=BookingStatus(model.status),
        created_at=model.created_at,
        cancelled_at=model.cancelled_at,
    )


class SqlAlchemyResourceRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def create(self, name: str, capacity: int, location: str | None) -> Resource:
        model = ResourceModel(name=name, capacity=capacity, location=location)
        self._session.add(model)
        self._session.commit()
        self._session.refresh(model)
        return _to_resource(model)

    def get(self, resource_id: UUID) -> Resource | None:
        model = self._session.get(ResourceModel, resource_id)
        return _to_resource(model) if model else None

    def list(self) -> list[Resource]:
        models = self._session.scalars(select(ResourceModel).order_by(ResourceModel.created_at)).all()
        return [_to_resource(m) for m in models]


class SqlAlchemyBookingRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def create_active_booking(
        self,
        resource_id: UUID,
        requester_email: str,
        start_time: datetime,
        end_time: datetime,
    ) -> Booking:
        session = self._session
        try:
            session.execute(
                select(ResourceModel.id).where(ResourceModel.id == resource_id).with_for_update()
            ).one()

            conflict = session.execute(
                select(BookingModel.id).where(
                    BookingModel.resource_id == resource_id,
                    BookingModel.status == BookingStatus.ACTIVE.value,
                    BookingModel.start_time < end_time,
                    BookingModel.end_time > start_time,
                )
            ).first()
            if conflict is not None:
                raise OverlappingBookingError("Resource is already booked for part of this time window.")

            model = BookingModel(
                resource_id=resource_id,
                requester_email=requester_email,
                start_time=start_time,
                end_time=end_time,
                status=BookingStatus.ACTIVE.value,
            )
            session.add(model)
            session.commit()
            session.refresh(model)
            return _to_booking(model)
        except OverlappingBookingError:
            session.rollback()
            raise
        except IntegrityError:
            session.rollback()
            raise OverlappingBookingError("Resource is already booked for part of this time window.")

    def get(self, booking_id: UUID) -> Booking | None:
        model = self._session.get(BookingModel, booking_id)
        return _to_booking(model) if model else None

    def cancel(self, booking_id: UUID, cancelled_at: datetime) -> Booking:
        # A conditional UPDATE (not a read-then-write) so two concurrent cancel
        # calls for the same booking can't both succeed: Postgres serializes
        # concurrent UPDATEs on the same row, and only the first to commit
        # matches status = 'ACTIVE' — the second gets rowcount == 0.
        session = self._session
        result = session.execute(
            update(BookingModel)
            .where(BookingModel.id == booking_id, BookingModel.status == BookingStatus.ACTIVE.value)
            .values(status=BookingStatus.CANCELLED.value, cancelled_at=cancelled_at)
        )
        if result.rowcount == 0:
            session.rollback()
            raise BookingAlreadyCancelledError("Booking is already cancelled.")
        session.commit()
        model = session.get(BookingModel, booking_id)
        return _to_booking(model)

    def lock_requester(self, requester_email: str) -> None:
        # Transaction-scoped advisory lock keyed by the requester's email hash —
        # serializes this requester's concurrent booking attempts (across any
        # resource) so the quota count-then-insert sequence below is atomic.
        # Released automatically on commit/rollback, no unlock call needed.
        self._session.execute(text("SELECT pg_advisory_xact_lock(hashtext(:email))"), {"email": requester_email})

    def count_active_for_requester(self, requester_email: str) -> int:
        count = self._session.scalar(
            select(func.count())
            .select_from(BookingModel)
            .where(
                BookingModel.requester_email == requester_email,
                BookingModel.status == BookingStatus.ACTIVE.value,
            )
        )
        return count or 0

    def find_conflicts(self, resource_id: UUID, start_time: datetime, end_time: datetime) -> list[Booking]:
        models = self._session.scalars(
            select(BookingModel).where(
                BookingModel.resource_id == resource_id,
                BookingModel.status == BookingStatus.ACTIVE.value,
                BookingModel.start_time < end_time,
                BookingModel.end_time > start_time,
            )
        ).all()
        return [_to_booking(m) for m in models]

    def list_for_resource(self, resource_id: UUID) -> list[Booking]:
        models = self._session.scalars(
            select(BookingModel).where(BookingModel.resource_id == resource_id).order_by(BookingModel.start_time)
        ).all()
        return [_to_booking(m) for m in models]
