import threading
from concurrent.futures import ThreadPoolExecutor
from uuid import UUID

import pytest
from sqlalchemy import func, select

from booking_api.domain.entities import BookingStatus
from booking_api.infra.models import BookingModel

pytestmark = pytest.mark.concurrency

RESOURCE_COUNT = 10


class TestLockIsPerResourceNotGlobal:
    """Proves the SELECT ... FOR UPDATE lock in create_active_booking serializes
    writers per-resource, not globally — otherwise the system would not scale
    beyond a single resource under concurrent load."""

    def test_concurrent_bookings_on_different_resources_all_succeed(self, client, future_slot, db_session):
        resource_ids = []
        for i in range(RESOURCE_COUNT):
            res = client.post("/resources", json={"name": f"Sala {i}", "capacity": 4})
            assert res.status_code == 201
            resource_ids.append(res.json()["id"])

        barrier = threading.Barrier(RESOURCE_COUNT)

        def attempt(indexed: tuple[int, str]) -> int:
            i, resource_id = indexed
            barrier.wait()
            body = {
                # Distinct requesters: reusing one email here would trip the
                # per-requester quota rule (R7) instead of exercising the
                # per-resource lock this test is actually about.
                "requester_email": f"user{i}@example.com",
                "start_time": future_slot.start.isoformat(),
                "end_time": future_slot.end.isoformat(),
            }
            response = client.post(f"/resources/{resource_id}/bookings", json=body)
            return response.status_code

        with ThreadPoolExecutor(max_workers=RESOURCE_COUNT) as pool:
            results = list(pool.map(attempt, enumerate(resource_ids)))

        assert results.count(201) == RESOURCE_COUNT, f"expected all bookings to succeed, got: {results}"

        active_in_db = db_session.scalar(
            select(func.count())
            .select_from(BookingModel)
            .where(
                BookingModel.resource_id.in_([UUID(rid) for rid in resource_ids]),
                BookingModel.status == BookingStatus.ACTIVE.value,
            )
        )
        assert active_in_db == RESOURCE_COUNT
