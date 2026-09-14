from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


class ResourceCreate(BaseModel):
    name: str
    capacity: int = Field(gt=0)
    location: str | None = None


class ResourceOut(BaseModel):
    id: UUID
    name: str
    capacity: int
    location: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class BookingCreate(BaseModel):
    requester_email: EmailStr
    start_time: datetime
    end_time: datetime


class BookingOut(BaseModel):
    id: UUID
    resource_id: UUID
    requester_email: EmailStr
    start_time: datetime
    end_time: datetime
    status: Literal["ACTIVE", "CANCELLED"]
    created_at: datetime
    cancelled_at: datetime | None

    model_config = {"from_attributes": True}


class AvailabilityOut(BaseModel):
    resource_id: UUID
    query_start: datetime
    query_end: datetime
    is_available: bool
    conflicting_bookings: list[BookingOut]


class ErrorResponse(BaseModel):
    error_code: str
    message: str
    details: dict | None = None
