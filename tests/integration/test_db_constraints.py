from datetime import timedelta
from uuid import UUID

import pytest
from sqlalchemy.exc import IntegrityError

from booking_api.domain.entities import BookingStatus
from booking_api.infra.models import BookingModel

pytestmark = pytest.mark.integration


def _insert(db_session, resource_id, start, end, status=BookingStatus.ACTIVE) -> None:
    db_session.add(
        BookingModel(
            resource_id=UUID(resource_id),
            requester_email="user@example.com",
            start_time=start,
            end_time=end,
            status=status.value,
        )
    )
    db_session.commit()


class TestExcludeConstraintIsTheFinalGuarantee:
    def test_overlapping_active_bookings_are_rejected_by_the_database(self, db_session, resource_id, future_slot):
        _insert(db_session, resource_id, future_slot.start, future_slot.end)

        with pytest.raises(IntegrityError, match="no_overlapping_active_bookings"):
            _insert(db_session, resource_id, future_slot.start + timedelta(minutes=30), future_slot.end + timedelta(minutes=30))

    def test_adjacent_bookings_are_allowed(self, db_session, resource_id, future_slot):
        _insert(db_session, resource_id, future_slot.start, future_slot.end)
        _insert(db_session, resource_id, future_slot.end, future_slot.end + timedelta(hours=1))

    def test_cancelled_booking_does_not_block_the_slot(self, db_session, resource_id, future_slot):
        _insert(db_session, resource_id, future_slot.start, future_slot.end, status=BookingStatus.CANCELLED)
        _insert(db_session, resource_id, future_slot.start, future_slot.end)
