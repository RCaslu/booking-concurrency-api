from datetime import datetime, timedelta, timezone
from uuid import UUID

import pytest

from booking_api.domain.entities import BookingStatus
from booking_api.domain.exceptions import BookingAlreadyStartedError
from booking_api.infra.models import BookingModel
from booking_api.infra.repositories import SqlAlchemyBookingRepository

pytestmark = pytest.mark.integration


@pytest.fixture
def started_booking(db_session, resource_id) -> BookingModel:
    start = datetime.now(timezone.utc) - timedelta(minutes=5)
    model = BookingModel(
        resource_id=UUID(resource_id),
        requester_email="user@example.com",
        start_time=start,
        end_time=start + timedelta(hours=1),
        status=BookingStatus.ACTIVE.value,
    )
    db_session.add(model)
    db_session.commit()
    return model


class TestNotStartedIsCheckedByTheWriteItself:
    def test_reschedule_of_a_booking_that_already_started_is_rejected(self, db_session, resource_id, started_booking):
        original_start = started_booking.start_time
        target_start = datetime.now(timezone.utc) + timedelta(days=5)

        with pytest.raises(BookingAlreadyStartedError):
            SqlAlchemyBookingRepository(db_session).reschedule(
                started_booking.id, UUID(resource_id), target_start, target_start + timedelta(hours=1)
            )

        db_session.expire_all()
        assert db_session.get(BookingModel, started_booking.id).start_time == original_start

    def test_cancel_of_a_booking_that_already_started_is_rejected(self, db_session, started_booking):
        with pytest.raises(BookingAlreadyStartedError):
            SqlAlchemyBookingRepository(db_session).cancel(started_booking.id, cancelled_at=datetime.now(timezone.utc))

        db_session.expire_all()
        assert db_session.get(BookingModel, started_booking.id).status == BookingStatus.ACTIVE.value
