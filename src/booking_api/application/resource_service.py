from __future__ import annotations

from uuid import UUID

from booking_api.application.ports import ResourceRepository
from booking_api.domain.entities import Resource
from booking_api.domain.exceptions import ResourceNotFoundError


class ResourceService:
    def __init__(self, resource_repo: ResourceRepository) -> None:
        self._resource_repo = resource_repo

    def create_resource(self, name: str, capacity: int, location: str | None) -> Resource:
        return self._resource_repo.create(name=name, capacity=capacity, location=location)

    def list_resources(self) -> list[Resource]:
        return self._resource_repo.list()

    def get_resource(self, resource_id: UUID) -> Resource:
        resource = self._resource_repo.get(resource_id)
        if resource is None:
            raise ResourceNotFoundError(f"Resource {resource_id} not found.")
        return resource
