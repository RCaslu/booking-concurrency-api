import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from uuid import UUID

import pytest
from sqlalchemy import func, select

from booking_api.domain.entities import BookingStatus
from booking_api.domain.exceptions import BookingAlreadyStartedError
from booking_api.infra.repositories import SqlAlchemyBookingRepository
from booking_api.infra.models import BookingModel

pytestmark = pytest.mark.concurrency

CONCURRENT_REQUESTS = 20


def _create(client, resource_id, email, start, end) -> dict:
    response = client.post(
        f"/resources/{resource_id}/bookings",
        json={"requester_email": email, "start_time": start.isoformat(), "end_time": end.isoformat()},
    )
    assert response.status_code == 201, response.text
    return response.json()


def _active_overlapping(db_session, resource_id, start, end) -> int:
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


class TestRescheduleIsNotRaceable:

    def test_only_one_of_many_concurrent_reschedules_into_same_slot_wins(
        self, client, resource_id, future_slot, db_session
    ):
        booking_ids = [
            _create(
                client,
                resource_id,
                f"user{i}@example.com",
                future_slot.start + timedelta(hours=2 * i),
                future_slot.start + timedelta(hours=2 * i + 1),
            )["id"]
            for i in range(CONCURRENT_REQUESTS)
        ]
        target_start = future_slot.start + timedelta(days=5)
        target_end = target_start + timedelta(hours=1)
        barrier = threading.Barrier(CONCURRENT_REQUESTS)

        def attempt(booking_id: str) -> int:
            barrier.wait()
            return client.patch(
                f"/bookings/{booking_id}",
                json={"start_time": target_start.isoformat(), "end_time": target_end.isoformat()},
            ).status_code

        with ThreadPoolExecutor(max_workers=CONCURRENT_REQUESTS) as pool:
            results = list(pool.map(attempt, booking_ids))

        assert results.count(200) == 1, f"expected exactly one 200, got: {results}"
        assert results.count(409) == CONCURRENT_REQUESTS - 1
        assert _active_overlapping(db_session, resource_id, target_start, target_end) == 1

    def test_reschedule_racing_creations_for_same_slot_has_one_winner(
        self, client, resource_id, future_slot, db_session
    ):
        booking_id = _create(client, resource_id, "mover@example.com", future_slot.start, future_slot.end)["id"]
        target_start = future_slot.start + timedelta(days=5)
        target_end = target_start + timedelta(hours=1)
        window = {"start_time": target_start.isoformat(), "end_time": target_end.isoformat()}
        barrier = threading.Barrier(CONCURRENT_REQUESTS)

        def attempt(i: int) -> tuple[str, int]:
            barrier.wait()
            if i == 0:
                return "reschedule", client.patch(f"/bookings/{booking_id}", json=window).status_code
            body = {"requester_email": f"creator{i}@example.com", **window}
            return "create", client.post(f"/resources/{resource_id}/bookings", json=body).status_code

        with ThreadPoolExecutor(max_workers=CONCURRENT_REQUESTS) as pool:
            results = list(pool.map(attempt, range(CONCURRENT_REQUESTS)))

        winners = [r for r in results if r[1] in (200, 201)]
        assert len(winners) == 1, f"expected exactly one winner, got: {results}"
        assert sum(1 for r in results if r[1] == 409) == CONCURRENT_REQUESTS - 1
        assert _active_overlapping(db_session, resource_id, target_start, target_end) == 1

    def test_reschedule_racing_cancel_never_moves_a_cancelled_booking(
        self, client, resource_id, future_slot, db_session
    ):
        booking_id = _create(client, resource_id, "user@example.com", future_slot.start, future_slot.end)["id"]
        target_start = future_slot.start + timedelta(days=5)
        window = {"start_time": target_start.isoformat(), "end_time": (target_start + timedelta(hours=1)).isoformat()}
        barrier = threading.Barrier(2)

        def attempt(action: str) -> int:
            barrier.wait()
            if action == "cancel":
                return client.delete(f"/bookings/{booking_id}").status_code
            return client.patch(f"/bookings/{booking_id}", json=window).status_code

        with ThreadPoolExecutor(max_workers=2) as pool:
            cancel_status, reschedule_status = pool.map(attempt, ["cancel", "reschedule"])

        assert cancel_status == 200
        assert reschedule_status in (200, 409)
        final = db_session.get(BookingModel, UUID(booking_id))
        assert final.status == BookingStatus.CANCELLED.value
        expected_start = target_start if reschedule_status == 200 else future_slot.start
        assert final.start_time == expected_start

    def test_write_landing_after_start_is_rejected(self, client, resource_id, future_slot, db_session):
        booking_id = UUID(_create(client, resource_id, "user@example.com", future_slot.start, future_slot.end)["id"])
        target_start = future_slot.start + timedelta(days=5)

        with pytest.raises(BookingAlreadyStartedError):
            SqlAlchemyBookingRepository(db_session).reschedule(
                booking_id,
                UUID(resource_id),
                target_start,
                target_start + timedelta(hours=1),
                now=future_slot.start + timedelta(seconds=1),
            )

        db_session.expire_all()
        assert db_session.get(BookingModel, booking_id).start_time == future_slot.start
