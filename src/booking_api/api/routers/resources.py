from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from booking_api.api.deps import get_booking_service, get_db, get_resource_service
from booking_api.api.schemas import (
    AvailabilityOut,
    BookingCreate,
    BookingOut,
    ResourceCreate,
    ResourceOut,
)

router = APIRouter(prefix="/resources", tags=["resources"])


@router.post("", response_model=ResourceOut, status_code=status.HTTP_201_CREATED)
def create_resource(payload: ResourceCreate, db: Session = Depends(get_db)):
    resource = get_resource_service(db).create_resource(
        name=payload.name, capacity=payload.capacity, location=payload.location
    )
    return resource


@router.get("", response_model=list[ResourceOut])
def list_resources(db: Session = Depends(get_db)):
    return get_resource_service(db).list_resources()


@router.get("/{resource_id}", response_model=ResourceOut)
def get_resource(resource_id: UUID, db: Session = Depends(get_db)):
    return get_resource_service(db).get_resource(resource_id)


@router.get("/{resource_id}/availability", response_model=AvailabilityOut)
def check_availability(
    resource_id: UUID,
    start: datetime = Query(...),
    end: datetime = Query(...),
    db: Session = Depends(get_db),
):
    result = get_booking_service(db).check_availability(resource_id, start, end)
    return AvailabilityOut(
        resource_id=result.resource_id,
        query_start=result.query_start,
        query_end=result.query_end,
        is_available=result.is_available,
        conflicting_bookings=result.conflicting_bookings,
    )


@router.post("/{resource_id}/bookings", response_model=BookingOut, status_code=status.HTTP_201_CREATED)
def create_booking(resource_id: UUID, payload: BookingCreate, db: Session = Depends(get_db)):
    return get_booking_service(db).create_booking(
        resource_id=resource_id,
        requester_email=payload.requester_email,
        start_time=payload.start_time,
        end_time=payload.end_time,
    )


@router.get("/{resource_id}/bookings", response_model=list[BookingOut])
def list_bookings_for_resource(resource_id: UUID, db: Session = Depends(get_db)):
    return get_booking_service(db).list_bookings_for_resource(resource_id)
