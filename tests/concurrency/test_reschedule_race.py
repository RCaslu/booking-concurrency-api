import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from uuid import UUID

import pytest
from sqlalchemy import func, select

from booking_api.domain.entities import BookingStatus
from booking_api.infra.models import BookingModel

pytestmark = pytest.mark.concurrency

CONCURRENT_REQUESTS = 20


def _count_active_overlapping(db_session, resource_id, start, end) -> int:
    return db_session.scalar(
        select(func.count())
        .select_from(BookingModel)
        .where(
            BookingModel.resource_id == resource_id,
            BookingModel.status == BookingStatus.ACTIVE.value,
            BookingModel.start_time < end,
            BookingModel.end_time > start,
        )
    )


class TestRescheduleCannotOverlap:
    def test_concurrent_reschedules_to_the_same_slot_yield_one_winner(self, client, resource_id, future_slot, db_session):
        target_start = future_slot.start + timedelta(days=40)
        target_end = target_start + timedelta(hours=1)
        booking_ids = []
        for i in range(CONCURRENT_REQUESTS):
            start = future_slot.start + timedelta(days=i)
            created = client.post(
                f"/resources/{resource_id}/bookings",
                json={
                    "requester_email": f"mover{i}@example.com",
                    "start_time": start.isoformat(),
                    "end_time": (start + timedelta(hours=1)).isoformat(),
                },
            )
            assert created.status_code == 201, created.text
            booking_ids.append(created.json()["id"])

        barrier = threading.Barrier(CONCURRENT_REQUESTS)

        def attempt(booking_id: str) -> int:
            barrier.wait()
            response = client.patch(
                f"/bookings/{booking_id}",
                json={"start_time": target_start.isoformat(), "end_time": target_end.isoformat()},
            )
            return response.status_code

        with ThreadPoolExecutor(max_workers=CONCURRENT_REQUESTS) as pool:
            results = list(pool.map(attempt, booking_ids))

        assert results.count(200) == 1, f"expected exactly one 200, got: {results}"
        assert results.count(409) == CONCURRENT_REQUESTS - 1

        assert _count_active_overlapping(db_session, UUID(resource_id), target_start, target_end) == 1

    def test_reschedule_racing_creates_yields_one_winner(self, client, resource_id, future_slot, db_session):
        existing = client.post(
            f"/resources/{resource_id}/bookings",
            json={
                "requester_email": "mover@example.com",
                "start_time": future_slot.start.isoformat(),
                "end_time": future_slot.end.isoformat(),
            },
        )
        assert existing.status_code == 201, existing.text
        booking_id = existing.json()["id"]

        target_start = future_slot.start + timedelta(days=2)
        target_end = target_start + timedelta(hours=1)
        workers = CONCURRENT_REQUESTS
        barrier = threading.Barrier(workers)

        def reschedule() -> int:
            barrier.wait()
            return client.patch(
                f"/bookings/{booking_id}",
                json={"start_time": target_start.isoformat(), "end_time": target_end.isoformat()},
            ).status_code

        def create(i: int) -> int:
            barrier.wait()
            return client.post(
                f"/resources/{resource_id}/bookings",
                json={
                    "requester_email": f"creator{i}@example.com",
                    "start_time": target_start.isoformat(),
                    "end_time": target_end.isoformat(),
                },
            ).status_code

        with ThreadPoolExecutor(max_workers=workers) as pool:
            reschedule_future = pool.submit(reschedule)
            create_futures = [pool.submit(create, i) for i in range(workers - 1)]
            results = [reschedule_future.result(), *[f.result() for f in create_futures]]

        successes = results.count(200) + results.count(201)
        assert successes == 1, f"expected exactly one success, got: {results}"
        assert results.count(409) == workers - 1
        assert _count_active_overlapping(db_session, UUID(resource_id), target_start, target_end) == 1
