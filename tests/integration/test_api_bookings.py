from datetime import timedelta
from uuid import uuid4

import pytest

from booking_api.infra.repositories import SqlAlchemyBookingRepository

pytestmark = pytest.mark.integration


def _booking_payload(slot, email="user@example.com"):
    return {
        "requester_email": email,
        "start_time": slot.start.isoformat(),
        "end_time": slot.end.isoformat(),
    }


class TestCreateBooking:
    def test_create_booking_returns_201(self, client, resource_id, future_slot):
        response = client.post(f"/resources/{resource_id}/bookings", json=_booking_payload(future_slot))

        assert response.status_code == 201
        body = response.json()
        assert body["resource_id"] == resource_id
        assert body["status"] == "ACTIVE"

    def test_create_booking_for_unknown_resource_returns_404(self, client, future_slot):
        response = client.post(f"/resources/{uuid4()}/bookings", json=_booking_payload(future_slot))

        assert response.status_code == 404
        assert response.json()["error_code"] == "RESOURCE_NOT_FOUND"

    def test_create_booking_with_end_before_start_returns_422(self, client, resource_id, future_slot):
        payload = _booking_payload(future_slot)
        payload["start_time"], payload["end_time"] = payload["end_time"], payload["start_time"]

        response = client.post(f"/resources/{resource_id}/bookings", json=payload)

        assert response.status_code == 422
        assert response.json()["error_code"] == "INVALID_TIME_WINDOW"

    def test_create_booking_with_invalid_email_returns_422(self, client, resource_id, future_slot):
        response = client.post(
            f"/resources/{resource_id}/bookings", json=_booking_payload(future_slot, email="not-an-email")
        )

        assert response.status_code == 422

    def test_create_booking_overlapping_existing_returns_409(self, client, resource_id, future_slot):
        client.post(f"/resources/{resource_id}/bookings", json=_booking_payload(future_slot))

        response = client.post(f"/resources/{resource_id}/bookings", json=_booking_payload(future_slot))

        assert response.status_code == 409
        assert response.json()["error_code"] == "OVERLAPPING_BOOKING"

    def test_create_booking_adjacent_to_existing_returns_201(self, client, resource_id, future_slot):
        """A meeting ending exactly when another begins must not conflict (half-open interval)."""
        client.post(f"/resources/{resource_id}/bookings", json=_booking_payload(future_slot))

        next_slot_payload = {
            "requester_email": "another@example.com",
            "start_time": future_slot.end.isoformat(),
            "end_time": (future_slot.end + timedelta(hours=1)).isoformat(),
        }
        response = client.post(f"/resources/{resource_id}/bookings", json=next_slot_payload)

        assert response.status_code == 201

    def test_create_fourth_booking_for_same_requester_returns_409(self, client, resource_id, future_slot):
        for i in range(3):
            payload = {
                "requester_email": "frequent@example.com",
                "start_time": (future_slot.start + timedelta(hours=3 * i)).isoformat(),
                "end_time": (future_slot.start + timedelta(hours=3 * i, minutes=30)).isoformat(),
            }
            assert client.post(f"/resources/{resource_id}/bookings", json=payload).status_code == 201

        payload = {
            "requester_email": "frequent@example.com",
            "start_time": (future_slot.start + timedelta(hours=30)).isoformat(),
            "end_time": (future_slot.start + timedelta(hours=30, minutes=30)).isoformat(),
        }
        response = client.post(f"/resources/{resource_id}/bookings", json=payload)

        assert response.status_code == 409
        assert response.json()["error_code"] == "BOOKING_QUOTA_EXCEEDED"


class TestGetBooking:
    def test_get_unknown_booking_returns_404(self, client):
        response = client.get(f"/bookings/{uuid4()}")

        assert response.status_code == 404
        assert response.json()["error_code"] == "BOOKING_NOT_FOUND"


class TestCancelBooking:
    def test_cancel_active_future_booking_returns_200(self, client, resource_id, future_slot):
        created = client.post(f"/resources/{resource_id}/bookings", json=_booking_payload(future_slot)).json()

        response = client.delete(f"/bookings/{created['id']}")

        assert response.status_code == 200
        assert response.json()["status"] == "CANCELLED"

    def test_cancel_unknown_booking_returns_404(self, client):
        response = client.delete(f"/bookings/{uuid4()}")

        assert response.status_code == 404

    def test_cancel_already_cancelled_booking_returns_409(self, client, resource_id, future_slot):
        created = client.post(f"/resources/{resource_id}/bookings", json=_booking_payload(future_slot)).json()
        client.delete(f"/bookings/{created['id']}")

        response = client.delete(f"/bookings/{created['id']}")

        assert response.status_code == 409
        assert response.json()["error_code"] == "BOOKING_ALREADY_CANCELLED"

    def test_cancel_booking_that_already_started_returns_409(self, client, resource_id, future_slot, db_session):
        # The API refuses to create a booking with a past start_time (R2), so a
        # started booking is set up directly through the repository, bypassing
        # service-level validation the same way a scheduler/cron would after
        # the start_time naturally elapses.
        repo = SqlAlchemyBookingRepository(db_session)
        started = repo.create_active_booking(
            resource_id=resource_id,
            requester_email="user@example.com",
            start_time=future_slot.start - timedelta(days=2),
            end_time=future_slot.start - timedelta(days=2) + timedelta(hours=1),
        )

        response = client.delete(f"/bookings/{started.id}")

        assert response.status_code == 409
        assert response.json()["error_code"] == "BOOKING_ALREADY_STARTED"


class TestAvailability:
    def test_available_when_no_bookings(self, client, resource_id, future_slot):
        response = client.get(
            f"/resources/{resource_id}/availability",
            params={"start": future_slot.start.isoformat(), "end": future_slot.end.isoformat()},
        )

        assert response.status_code == 200
        assert response.json()["is_available"] is True

    def test_unavailable_when_overlapping_booking_exists(self, client, resource_id, future_slot):
        client.post(f"/resources/{resource_id}/bookings", json=_booking_payload(future_slot))

        response = client.get(
            f"/resources/{resource_id}/availability",
            params={"start": future_slot.start.isoformat(), "end": future_slot.end.isoformat()},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["is_available"] is False
        assert len(body["conflicting_bookings"]) == 1

    def test_availability_for_unknown_resource_returns_404(self, client, future_slot):
        response = client.get(
            f"/resources/{uuid4()}/availability",
            params={"start": future_slot.start.isoformat(), "end": future_slot.end.isoformat()},
        )

        assert response.status_code == 404

    def test_availability_with_end_before_start_returns_422(self, client, resource_id, future_slot):
        response = client.get(
            f"/resources/{resource_id}/availability",
            params={"start": future_slot.end.isoformat(), "end": future_slot.start.isoformat()},
        )

        assert response.status_code == 422
        assert response.json()["error_code"] == "INVALID_TIME_WINDOW"

    def test_availability_for_a_past_window_is_allowed(self, client, resource_id):
        past_start = "2020-01-01T10:00:00Z"
        past_end = "2020-01-01T11:00:00Z"

        response = client.get(
            f"/resources/{resource_id}/availability",
            params={"start": past_start, "end": past_end},
        )

        assert response.status_code == 200
        assert response.json()["is_available"] is True
