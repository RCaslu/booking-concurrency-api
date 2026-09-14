from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from booking_api.domain.entities import Booking, BookingStatus
from booking_api.domain.exceptions import (
    BookingAlreadyCancelledError,
    BookingAlreadyStartedError,
    BookingQuotaExceededError,
    InvalidTimeWindowError,
)
from booking_api.domain.rules import (
    MAX_ACTIVE_BOOKINGS_PER_REQUESTER,
    MAX_BOOKING_DURATION,
    MIN_BOOKING_DURATION,
    check_booking_quota,
    ensure_cancellable,
    overlaps,
    validate_time_window,
)

pytestmark = pytest.mark.unit

NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _booking(start: datetime, status: BookingStatus = BookingStatus.ACTIVE) -> Booking:
    return Booking(
        id=uuid4(),
        resource_id=uuid4(),
        requester_email="user@example.com",
        start_time=start,
        end_time=start + timedelta(hours=1),
        status=status,
        created_at=NOW,
        cancelled_at=None,
    )


class TestOverlaps:
    def test_identical_windows_overlap(self):
        a_start = NOW + timedelta(hours=1)
        a_end = a_start + timedelta(hours=1)
        assert overlaps(a_start, a_end, a_start, a_end) is True

    def test_partial_overlap(self):
        a_start = NOW + timedelta(hours=1)
        a_end = a_start + timedelta(hours=1)
        b_start = a_start + timedelta(minutes=30)
        b_end = b_start + timedelta(hours=1)
        assert overlaps(a_start, a_end, b_start, b_end) is True

    def test_adjacent_windows_do_not_overlap(self):
        """The core edge case: a meeting ending at 15:00 must not conflict with one starting at 15:00."""
        a_start = NOW + timedelta(hours=1)
        a_end = a_start + timedelta(hours=1)
        b_start = a_end
        b_end = b_start + timedelta(hours=1)
        assert overlaps(a_start, a_end, b_start, b_end) is False

    def test_disjoint_windows_do_not_overlap(self):
        a_start = NOW + timedelta(hours=1)
        a_end = a_start + timedelta(hours=1)
        b_start = a_end + timedelta(hours=1)
        b_end = b_start + timedelta(hours=1)
        assert overlaps(a_start, a_end, b_start, b_end) is False

    def test_one_window_fully_contains_the_other(self):
        a_start = NOW + timedelta(hours=1)
        a_end = a_start + timedelta(hours=4)
        b_start = a_start + timedelta(hours=1)
        b_end = b_start + timedelta(hours=1)
        assert overlaps(a_start, a_end, b_start, b_end) is True


class TestValidateTimeWindow:
    def test_valid_window_does_not_raise(self):
        start = NOW + timedelta(hours=1)
        end = start + timedelta(hours=1)
        validate_time_window(start, end, NOW)

    def test_end_equal_to_start_is_invalid(self):
        start = NOW + timedelta(hours=1)
        with pytest.raises(InvalidTimeWindowError):
            validate_time_window(start, start, NOW)

    def test_end_before_start_is_invalid(self):
        start = NOW + timedelta(hours=2)
        end = NOW + timedelta(hours=1)
        with pytest.raises(InvalidTimeWindowError):
            validate_time_window(start, end, NOW)

    def test_start_in_the_past_is_invalid(self):
        start = NOW - timedelta(minutes=1)
        end = start + timedelta(hours=1)
        with pytest.raises(InvalidTimeWindowError):
            validate_time_window(start, end, NOW)

    def test_start_exactly_now_is_valid(self):
        end = NOW + MIN_BOOKING_DURATION
        validate_time_window(NOW, end, NOW)

    def test_duration_shorter_than_minimum_is_invalid(self):
        start = NOW + timedelta(hours=1)
        end = start + MIN_BOOKING_DURATION - timedelta(minutes=1)
        with pytest.raises(InvalidTimeWindowError):
            validate_time_window(start, end, NOW)

    def test_duration_exactly_minimum_is_valid(self):
        start = NOW + timedelta(hours=1)
        end = start + MIN_BOOKING_DURATION
        validate_time_window(start, end, NOW)

    def test_duration_exactly_maximum_is_valid(self):
        start = NOW + timedelta(hours=1)
        end = start + MAX_BOOKING_DURATION
        validate_time_window(start, end, NOW)

    def test_duration_longer_than_maximum_is_invalid(self):
        start = NOW + timedelta(hours=1)
        end = start + MAX_BOOKING_DURATION + timedelta(minutes=1)
        with pytest.raises(InvalidTimeWindowError):
            validate_time_window(start, end, NOW)


class TestCheckBookingQuota:
    def test_below_limit_does_not_raise(self):
        check_booking_quota(MAX_ACTIVE_BOOKINGS_PER_REQUESTER - 1)

    def test_at_limit_raises(self):
        with pytest.raises(BookingQuotaExceededError):
            check_booking_quota(MAX_ACTIVE_BOOKINGS_PER_REQUESTER)

    def test_above_limit_raises(self):
        with pytest.raises(BookingQuotaExceededError):
            check_booking_quota(MAX_ACTIVE_BOOKINGS_PER_REQUESTER + 1)


class TestEnsureCancellable:
    def test_active_future_booking_is_cancellable(self):
        booking = _booking(start=NOW + timedelta(hours=1))
        ensure_cancellable(booking, NOW)

    def test_already_cancelled_booking_raises(self):
        booking = _booking(start=NOW + timedelta(hours=1), status=BookingStatus.CANCELLED)
        with pytest.raises(BookingAlreadyCancelledError):
            ensure_cancellable(booking, NOW)

    def test_booking_that_already_started_raises(self):
        booking = _booking(start=NOW - timedelta(minutes=1))
        with pytest.raises(BookingAlreadyStartedError):
            ensure_cancellable(booking, NOW)

    def test_booking_starting_exactly_now_raises(self):
        booking = _booking(start=NOW)
        with pytest.raises(BookingAlreadyStartedError):
            ensure_cancellable(booking, NOW)
