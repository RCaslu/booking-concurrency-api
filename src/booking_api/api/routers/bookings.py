from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from booking_api.api.deps import get_booking_service, get_db
from booking_api.api.schemas import BookingOut

router = APIRouter(prefix="/bookings", tags=["bookings"])


@router.get("/{booking_id}", response_model=BookingOut)
def get_booking(booking_id: UUID, db: Session = Depends(get_db)):
    return get_booking_service(db).get_booking(booking_id)


@router.delete("/{booking_id}", response_model=BookingOut)
def cancel_booking(booking_id: UUID, db: Session = Depends(get_db)):
    return get_booking_service(db).cancel_booking(booking_id)
