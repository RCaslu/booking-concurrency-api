from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from uuid import UUID


class BookingStatus(str, Enum):
    ACTIVE = "ACTIVE"
    CANCELLED = "CANCELLED"


@dataclass(frozen=True)
class Resource:
    id: UUID
    name: str
    capacity: int
    location: str | None
    created_at: datetime


@dataclass(frozen=True)
class Booking:
    id: UUID
    resource_id: UUID
    requester_email: str
    start_time: datetime
    end_time: datetime
    status: BookingStatus
    created_at: datetime
    cancelled_at: datetime | None
