from __future__ import annotations

from datetime import datetime, timedelta

from booking_api.domain.entities import Booking, BookingStatus
from booking_api.domain.exceptions import (
    BookingAlreadyCancelledError,
    BookingAlreadyStartedError,
    BookingQuotaExceededError,
    InvalidTimeWindowError,
)

MIN_BOOKING_DURATION = timedelta(minutes=15)
MAX_BOOKING_DURATION = timedelta(hours=4)
MAX_ACTIVE_BOOKINGS_PER_REQUESTER = 3


def overlaps(start_a: datetime, end_a: datetime, start_b: datetime, end_b: datetime) -> bool:
    """Half-open interval overlap: [start_a, end_a) intersects [start_b, end_b)."""
    return start_a < end_b and end_a > start_b


def validate_query_window(start: datetime, end: datetime) -> None:
    """Shape-only validation (timezone-aware, end after start) shared by both a
    booking attempt and a plain availability query — a query may legitimately
    ask about the past or a full-day window, so the booking-specific rules
    (R2 not-in-the-past, R6 duration bounds) don't apply here."""
    if start.tzinfo is None or end.tzinfo is None:
        raise InvalidTimeWindowError("start_time and end_time must be timezone-aware.")
    if end <= start:
        raise InvalidTimeWindowError("end_time must be strictly after start_time.")


def validate_time_window(start: datetime, end: datetime, now: datetime) -> None:
    validate_query_window(start, end)
    if start < now:
        raise InvalidTimeWindowError("start_time cannot be in the past.")
    duration = end - start
    if duration < MIN_BOOKING_DURATION:
        raise InvalidTimeWindowError(f"Booking duration must be at least {MIN_BOOKING_DURATION}.")
    if duration > MAX_BOOKING_DURATION:
        raise InvalidTimeWindowError(f"Booking duration must be at most {MAX_BOOKING_DURATION}.")


def check_booking_quota(active_bookings_count: int) -> None:
    if active_bookings_count >= MAX_ACTIVE_BOOKINGS_PER_REQUESTER:
        raise BookingQuotaExceededError(
            f"Requester already has {active_bookings_count} active bookings "
            f"(limit is {MAX_ACTIVE_BOOKINGS_PER_REQUESTER})."
        )


def ensure_cancellable(booking: Booking, now: datetime) -> None:
    if booking.status == BookingStatus.CANCELLED:
        raise BookingAlreadyCancelledError("Booking is already cancelled.")
    if now >= booking.start_time:
        raise BookingAlreadyStartedError("Booking cannot be cancelled after it has started.")
