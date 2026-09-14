import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

pytestmark = pytest.mark.concurrency

CONCURRENT_REQUESTS = 20


class TestCancelIsNotRaceable:
    """Found by AI review: cancel() used to be a read-then-write with no lock or
    conditional WHERE clause, so two concurrent DELETE calls for the same
    booking could both succeed instead of the second getting 409."""

    def test_only_one_cancel_succeeds_for_the_same_booking(self, client, resource_id, future_slot):
        created = client.post(
            f"/resources/{resource_id}/bookings",
            json={
                "requester_email": "user@example.com",
                "start_time": future_slot.start.isoformat(),
                "end_time": future_slot.end.isoformat(),
            },
        ).json()
        booking_id = created["id"]

        barrier = threading.Barrier(CONCURRENT_REQUESTS)

        def attempt(_: int) -> int:
            barrier.wait()
            return client.delete(f"/bookings/{booking_id}").status_code

        with ThreadPoolExecutor(max_workers=CONCURRENT_REQUESTS) as pool:
            results = list(pool.map(attempt, range(CONCURRENT_REQUESTS)))

        assert results.count(200) == 1, f"expected exactly one 200, got: {results}"
        assert results.count(409) == CONCURRENT_REQUESTS - 1
