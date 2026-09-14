from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest

from booking_api.application.booking_service import BookingService
from booking_api.domain.entities import Booking, BookingStatus, Resource
from booking_api.domain.exceptions import (
    BookingNotFoundError,
    BookingQuotaExceededError,
    OverlappingBookingError,
    ResourceNotFoundError,
)
from booking_api.domain.rules import overlaps

pytestmark = pytest.mark.unit

NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


class FakeResourceRepository:
    def __init__(self) -> None:
        self._resources: dict[UUID, Resource] = {}

    def add(self, resource: Resource) -> None:
        self._resources[resource.id] = resource

    def create(self, name: str, capacity: int, location: str | None) -> Resource:
        resource = Resource(id=uuid4(), name=name, capacity=capacity, location=location, created_at=NOW)
        self._resources[resource.id] = resource
        return resource

    def get(self, resource_id: UUID) -> Resource | None:
        return self._resources.get(resource_id)

    def list(self) -> list[Resource]:
        return list(self._resources.values())


class FakeBookingRepository:
    """In-memory fake — no real concurrency guarantee, only used to test
    BookingService orchestration logic in isolation from any database."""

    def __init__(self) -> None:
        self._bookings: dict[UUID, Booking] = {}

    def create_active_booking(
        self, resource_id: UUID, requester_email: str, start_time: datetime, end_time: datetime
    ) -> Booking:
        for existing in self._bookings.values():
            if (
                existing.resource_id == resource_id
                and existing.status == BookingStatus.ACTIVE
                and overlaps(existing.start_time, existing.end_time, start_time, end_time)
            ):
                raise OverlappingBookingError("Resource is already booked for part of this time window.")

        booking = Booking(
            id=uuid4(),
            resource_id=resource_id,
            requester_email=requester_email,
            start_time=start_time,
            end_time=end_time,
            status=BookingStatus.ACTIVE,
            created_at=NOW,
            cancelled_at=None,
        )
        self._bookings[booking.id] = booking
        return booking

    def get(self, booking_id: UUID) -> Booking | None:
        return self._bookings.get(booking_id)

    def cancel(self, booking_id: UUID, cancelled_at: datetime) -> Booking:
        booking = self._bookings[booking_id]
        cancelled = Booking(
            id=booking.id,
            resource_id=booking.resource_id,
            requester_email=booking.requester_email,
            start_time=booking.start_time,
            end_time=booking.end_time,
            status=BookingStatus.CANCELLED,
            created_at=booking.created_at,
            cancelled_at=cancelled_at,
        )
        self._bookings[booking_id] = cancelled
        return cancelled

    def count_active_for_requester(self, requester_email: str) -> int:
        return sum(
            1
            for b in self._bookings.values()
            if b.requester_email == requester_email and b.status == BookingStatus.ACTIVE
        )

    def find_conflicts(self, resource_id: UUID, start_time: datetime, end_time: datetime) -> list[Booking]:
        return [
            b
            for b in self._bookings.values()
            if b.resource_id == resource_id
            and b.status == BookingStatus.ACTIVE
            and overlaps(b.start_time, b.end_time, start_time, end_time)
        ]

    def list_for_resource(self, resource_id: UUID) -> list[Booking]:
        return [b for b in self._bookings.values() if b.resource_id == resource_id]


@pytest.fixture
def resource_repo() -> FakeResourceRepository:
    return FakeResourceRepository()


@pytest.fixture
def booking_repo() -> FakeBookingRepository:
    return FakeBookingRepository()


@pytest.fixture
def service(resource_repo: FakeResourceRepository, booking_repo: FakeBookingRepository) -> BookingService:
    return BookingService(resource_repo, booking_repo, clock=lambda: NOW)


@pytest.fixture
def resource(resource_repo: FakeResourceRepository) -> Resource:
    resource = Resource(id=uuid4(), name="Sala A", capacity=8, location=None, created_at=NOW)
    resource_repo.add(resource)
    return resource


class TestCreateBooking:
    def test_creates_booking_for_existing_resource(self, service: BookingService, resource: Resource):
        start = NOW + timedelta(hours=1)
        end = start + timedelta(hours=1)

        booking = service.create_booking(resource.id, "user@example.com", start, end)

        assert booking.resource_id == resource.id
        assert booking.status == BookingStatus.ACTIVE

    def test_raises_when_resource_does_not_exist(self, service: BookingService):
        start = NOW + timedelta(hours=1)
        end = start + timedelta(hours=1)

        with pytest.raises(ResourceNotFoundError):
            service.create_booking(uuid4(), "user@example.com", start, end)

    def test_raises_on_overlap_for_same_resource(self, service: BookingService, resource: Resource):
        start = NOW + timedelta(hours=1)
        end = start + timedelta(hours=1)
        service.create_booking(resource.id, "user@example.com", start, end)

        with pytest.raises(OverlappingBookingError):
            service.create_booking(resource.id, "another@example.com", start, end)

    def test_does_not_raise_on_overlap_for_different_resource(
        self, service: BookingService, resource_repo: FakeResourceRepository, resource: Resource
    ):
        other_resource = Resource(id=uuid4(), name="Sala B", capacity=4, location=None, created_at=NOW)
        resource_repo.add(other_resource)
        start = NOW + timedelta(hours=1)
        end = start + timedelta(hours=1)
        service.create_booking(resource.id, "user@example.com", start, end)

        booking = service.create_booking(other_resource.id, "user@example.com", start, end)

        assert booking.resource_id == other_resource.id

    def test_raises_when_requester_quota_exceeded(self, service: BookingService, resource: Resource):
        for i in range(3):
            start = NOW + timedelta(hours=1 + i * 2)
            end = start + timedelta(hours=1)
            service.create_booking(resource.id, "user@example.com", start, end)

        start = NOW + timedelta(hours=10)
        end = start + timedelta(hours=1)
        with pytest.raises(BookingQuotaExceededError):
            service.create_booking(resource.id, "user@example.com", start, end)


class TestCancelBooking:
    def test_cancels_active_future_booking(self, service: BookingService, resource: Resource):
        start = NOW + timedelta(hours=1)
        end = start + timedelta(hours=1)
        booking = service.create_booking(resource.id, "user@example.com", start, end)

        cancelled = service.cancel_booking(booking.id)

        assert cancelled.status == BookingStatus.CANCELLED
        assert cancelled.cancelled_at == NOW

    def test_raises_for_unknown_booking(self, service: BookingService):
        with pytest.raises(BookingNotFoundError):
            service.cancel_booking(uuid4())


class TestCheckAvailability:
    def test_available_when_no_conflicts(self, service: BookingService, resource: Resource):
        start = NOW + timedelta(hours=1)
        end = start + timedelta(hours=1)

        result = service.check_availability(resource.id, start, end)

        assert result.is_available is True
        assert result.conflicting_bookings == []

    def test_unavailable_when_conflicting_booking_exists(self, service: BookingService, resource: Resource):
        start = NOW + timedelta(hours=1)
        end = start + timedelta(hours=1)
        service.create_booking(resource.id, "user@example.com", start, end)

        result = service.check_availability(resource.id, start, end)

        assert result.is_available is False
        assert len(result.conflicting_bookings) == 1

    def test_raises_when_resource_does_not_exist(self, service: BookingService):
        with pytest.raises(ResourceNotFoundError):
            service.check_availability(uuid4(), NOW, NOW + timedelta(hours=1))
