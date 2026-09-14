import threading
from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import func, select

from booking_api.domain.entities import BookingStatus
from booking_api.infra.models import BookingModel

pytestmark = pytest.mark.concurrency

CONCURRENT_REQUESTS = 20


def _count_active_bookings(db_session, resource_id) -> int:
    return db_session.scalar(
        select(func.count())
        .select_from(BookingModel)
        .where(
            BookingModel.resource_id == resource_id,
            BookingModel.status == BookingStatus.ACTIVE.value,
        )
    )


class TestDoubleBookingIsImpossible:
    """The core guarantee of this project: N truly concurrent requests for the
    exact same resource/time-slot must yield exactly one winner, deterministically,
    with no flakiness — enforced at the database level (SELECT ... FOR UPDATE +
    EXCLUDE constraint), not by application-level timing tricks."""

    def test_only_one_booking_wins_for_same_slot(self, client, resource_id, future_slot, db_session):
        barrier = threading.Barrier(CONCURRENT_REQUESTS)
        payload = {
            "requester_email_prefix": "user",
            "start_time": future_slot.start.isoformat(),
            "end_time": future_slot.end.isoformat(),
        }

        def attempt(i: int) -> int:
            barrier.wait()
            body = {
                "requester_email": f"user{i}@example.com",
                "start_time": payload["start_time"],
                "end_time": payload["end_time"],
            }
            response = client.post(f"/resources/{resource_id}/bookings", json=body)
            return response.status_code

        with ThreadPoolExecutor(max_workers=CONCURRENT_REQUESTS) as pool:
            results = list(pool.map(attempt, range(CONCURRENT_REQUESTS)))

        assert results.count(201) == 1, f"expected exactly one 201, got: {results}"
        assert results.count(409) == CONCURRENT_REQUESTS - 1

        active_in_db = _count_active_bookings(db_session, resource_id)
        assert active_in_db == 1, "the database must reflect exactly one active booking, not just the API response"

    def test_repeated_runs_are_not_flaky(self, client, resource_id, future_slot, db_session):
        """Runs the same race multiple times against fresh, non-overlapping
        slots — a single flaky run here would indicate the guarantee is timing-
        dependent rather than structural."""
        from datetime import timedelta

        for run in range(3):
            slot_start = future_slot.start + timedelta(days=run)
            slot_end = slot_start + timedelta(hours=1)
            barrier = threading.Barrier(CONCURRENT_REQUESTS)

            def attempt(i: int, start=slot_start, end=slot_end) -> int:
                barrier.wait()
                body = {
                    "requester_email": f"run{run}-user{i}@example.com",
                    "start_time": start.isoformat(),
                    "end_time": end.isoformat(),
                }
                response = client.post(f"/resources/{resource_id}/bookings", json=body)
                return response.status_code

            with ThreadPoolExecutor(max_workers=CONCURRENT_REQUESTS) as pool:
                results = list(pool.map(attempt, range(CONCURRENT_REQUESTS)))

            assert results.count(201) == 1, f"run {run} failed: {results}"
