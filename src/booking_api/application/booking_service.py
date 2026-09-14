from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable
from uuid import UUID

from booking_api.application.ports import BookingRepository, ResourceRepository
from booking_api.domain.entities import Booking
from booking_api.domain.exceptions import BookingNotFoundError, ResourceNotFoundError
from booking_api.domain.rules import (
    check_booking_quota,
    ensure_cancellable,
    validate_query_window,
    validate_time_window,
)


@dataclass(frozen=True)
class AvailabilityResult:
    resource_id: UUID
    query_start: datetime
    query_end: datetime
    is_available: bool
    conflicting_bookings: list[Booking]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class BookingService:
    def __init__(
        self,
        resource_repo: ResourceRepository,
        booking_repo: BookingRepository,
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        self._resource_repo = resource_repo
        self._booking_repo = booking_repo
        self._clock = clock

    def create_booking(
        self,
        resource_id: UUID,
        requester_email: str,
        start_time: datetime,
        end_time: datetime,
    ) -> Booking:
        now = self._clock()
        validate_time_window(start_time, end_time, now)

        if self._resource_repo.get(resource_id) is None:
            raise ResourceNotFoundError(f"Resource {resource_id} not found.")

        self._booking_repo.lock_requester(requester_email)
        active_count = self._booking_repo.count_active_for_requester(requester_email)
        check_booking_quota(active_count)

        return self._booking_repo.create_active_booking(resource_id, requester_email, start_time, end_time)

    def cancel_booking(self, booking_id: UUID) -> Booking:
        booking = self._booking_repo.get(booking_id)
        if booking is None:
            raise BookingNotFoundError(f"Booking {booking_id} not found.")

        now = self._clock()
        ensure_cancellable(booking, now)
        return self._booking_repo.cancel(booking_id, cancelled_at=now)

    def check_availability(self, resource_id: UUID, start_time: datetime, end_time: datetime) -> AvailabilityResult:
        validate_query_window(start_time, end_time)

        if self._resource_repo.get(resource_id) is None:
            raise ResourceNotFoundError(f"Resource {resource_id} not found.")

        conflicts = self._booking_repo.find_conflicts(resource_id, start_time, end_time)
        return AvailabilityResult(
            resource_id=resource_id,
            query_start=start_time,
            query_end=end_time,
            is_available=not conflicts,
            conflicting_bookings=conflicts,
        )

    def list_bookings_for_resource(self, resource_id: UUID) -> list[Booking]:
        if self._resource_repo.get(resource_id) is None:
            raise ResourceNotFoundError(f"Resource {resource_id} not found.")
        return self._booking_repo.list_for_resource(resource_id)

    def get_booking(self, booking_id: UUID) -> Booking:
        booking = self._booking_repo.get(booking_id)
        if booking is None:
            raise BookingNotFoundError(f"Booking {booking_id} not found.")
        return booking
