import threading
from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import func, select

from booking_api.domain.entities import BookingStatus
from booking_api.domain.rules import MAX_ACTIVE_BOOKINGS_PER_REQUESTER
from booking_api.infra.models import BookingModel

pytestmark = pytest.mark.concurrency

CONCURRENT_REQUESTS = 10


class TestRequesterQuotaIsNotRaceable:
    """R7 (max active bookings per requester) is checked via a separate read
    before the insert, not inside the same per-resource row lock
    create_active_booking uses for R3. BookingService.create_booking() closes
    this with BookingRepository.lock_requester() - a transaction-scoped Postgres
    advisory lock keyed by the requester's email - called before the count, so
    concurrent requests from the same requester (even across different
    resources) are serialized instead of all reading a count below the limit
    before any of them commits. This test is the proof that lock actually
    holds under real concurrent load."""

    def test_same_requester_cannot_exceed_quota_across_different_resources(self, client, future_slot, db_session):
        resource_ids = []
        for i in range(CONCURRENT_REQUESTS):
            res = client.post("/resources", json={"name": f"Sala Quota {i}", "capacity": 4})
            assert res.status_code == 201
            resource_ids.append(res.json()["id"])

        barrier = threading.Barrier(CONCURRENT_REQUESTS)

        def attempt(resource_id: str) -> int:
            barrier.wait()
            body = {
                "requester_email": "same-user@example.com",
                "start_time": future_slot.start.isoformat(),
                "end_time": future_slot.end.isoformat(),
            }
            response = client.post(f"/resources/{resource_id}/bookings", json=body)
            return response.status_code

        with ThreadPoolExecutor(max_workers=CONCURRENT_REQUESTS) as pool:
            results = list(pool.map(attempt, resource_ids))

        successes = results.count(201)
        assert successes == MAX_ACTIVE_BOOKINGS_PER_REQUESTER, (
            f"expected exactly {MAX_ACTIVE_BOOKINGS_PER_REQUESTER} successes, got {successes}: {results}"
        )

        active_in_db = db_session.scalar(
            select(func.count())
            .select_from(BookingModel)
            .where(
                BookingModel.requester_email == "same-user@example.com",
                BookingModel.status == BookingStatus.ACTIVE.value,
            )
        )
        assert active_in_db == MAX_ACTIVE_BOOKINGS_PER_REQUESTER
