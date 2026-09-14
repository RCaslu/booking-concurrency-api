from __future__ import annotations

from datetime import datetime
from typing import Protocol
from uuid import UUID

from booking_api.domain.entities import Booking, Resource


class ResourceRepository(Protocol):
    def create(self, name: str, capacity: int, location: str | None) -> Resource: ...

    def get(self, resource_id: UUID) -> Resource | None: ...

    def list(self) -> list[Resource]: ...


class BookingRepository(Protocol):
    def create_active_booking(
        self,
        resource_id: UUID,
        requester_email: str,
        start_time: datetime,
        end_time: datetime,
    ) -> Booking:
        """Atomically checks for overlaps and inserts the booking.

        Must raise booking_api.domain.exceptions.OverlappingBookingError if an
        ACTIVE booking already occupies any part of [start_time, end_time) for
        this resource. Implementations backed by a real database must guarantee
        this atomically under concurrent callers (see infra.repositories).
        """
        ...

    def get(self, booking_id: UUID) -> Booking | None: ...

    def cancel(self, booking_id: UUID, cancelled_at: datetime) -> Booking: ...

    def count_active_for_requester(self, requester_email: str) -> int: ...

    def find_conflicts(self, resource_id: UUID, start_time: datetime, end_time: datetime) -> list[Booking]: ...

    def list_for_resource(self, resource_id: UUID) -> list[Booking]: ...
