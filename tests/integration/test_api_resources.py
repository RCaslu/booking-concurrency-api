from uuid import uuid4

import pytest

pytestmark = pytest.mark.integration


class TestCreateResource:
    def test_create_resource_returns_201(self, client):
        response = client.post("/resources", json={"name": "Sala A", "capacity": 8, "location": "1º andar"})

        assert response.status_code == 201
        body = response.json()
        assert body["name"] == "Sala A"
        assert body["capacity"] == 8

    def test_create_resource_with_zero_capacity_returns_422(self, client):
        response = client.post("/resources", json={"name": "Sala A", "capacity": 0})

        assert response.status_code == 422

    def test_create_resource_with_negative_capacity_returns_422(self, client):
        response = client.post("/resources", json={"name": "Sala A", "capacity": -1})

        assert response.status_code == 422

    def test_create_resource_without_location_is_allowed(self, client):
        response = client.post("/resources", json={"name": "Sala A", "capacity": 8})

        assert response.status_code == 201
        assert response.json()["location"] is None


class TestGetResource:
    def test_get_existing_resource(self, client, resource):
        response = client.get(f"/resources/{resource['id']}")

        assert response.status_code == 200
        assert response.json()["id"] == resource["id"]

    def test_get_unknown_resource_returns_404(self, client):
        response = client.get(f"/resources/{uuid4()}")

        assert response.status_code == 404
        assert response.json()["error_code"] == "RESOURCE_NOT_FOUND"


class TestListResources:
    def test_list_returns_created_resource(self, client, resource):
        response = client.get("/resources")

        assert response.status_code == 200
        ids = [r["id"] for r in response.json()]
        assert resource["id"] in ids
