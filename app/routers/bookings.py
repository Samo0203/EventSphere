import secrets

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Booking, Event, TicketCategory, Payment
from app.schemas import BookingCreate
from app.security import get_current_user

router = APIRouter(
    prefix="/bookings",
    tags=["Booking Management"]
)


@router.post("/", status_code=status.HTTP_201_CREATED)
def create_booking(
    booking_data: BookingCreate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    try:
        # Check whether event exists
        event = db.query(Event).filter(
            Event.id == booking_data.event_id
        ).first()

        if not event:
            raise HTTPException(
                status_code=404,
                detail="Event not found"
            )

        if event.status == "cancelled":
            raise HTTPException(
                status_code=400,
                detail="This event has been cancelled"
            )

        # Check ticket category
        category = db.query(TicketCategory).filter(
            TicketCategory.id == booking_data.ticket_category_id,
            TicketCategory.event_id == booking_data.event_id
        ).first()

        if not category:
            raise HTTPException(
                status_code=404,
                detail="Ticket category not found for this event"
            )

        # Atomically reduce available ticket quantity
        result = db.query(TicketCategory).filter(
            TicketCategory.id == booking_data.ticket_category_id,
            TicketCategory.available_quantity >= booking_data.quantity
        ).update(
            {
                TicketCategory.available_quantity:
                    TicketCategory.available_quantity - booking_data.quantity
            },
            synchronize_session=False
        )

        if result == 0:
            db.rollback()
            raise HTTPException(
                status_code=400,
                detail="Not enough tickets available"
            )

        # Calculate booking amount
        total_amount = category.price * booking_data.quantity

        # Create booking
        new_booking = Booking(
            user_id=current_user.id,
            event_id=booking_data.event_id,
            ticket_category_id=booking_data.ticket_category_id,
            quantity=booking_data.quantity,
            total_amount=total_amount,
            status="confirmed"
        )

        db.add(new_booking)
        db.flush()

        # Generate simulated payment reference
        payment_reference = "PAY-" + secrets.token_hex(6).upper()

        new_payment = Payment(
            booking_id=new_booking.id,
            payment_reference=payment_reference,
            amount=total_amount,
            status="success"
        )

        db.add(new_payment)
        db.commit()
        db.refresh(new_booking)

        return {
            "message": "Booking created successfully",
            "booking_id": new_booking.id,
            "event_id": new_booking.event_id,
            "ticket_category": category.name,
            "quantity": new_booking.quantity,
            "total_amount": float(new_booking.total_amount),
            "booking_status": new_booking.status,
            "payment_reference": payment_reference,
            "payment_status": "success"
        }

    except HTTPException:
        raise

    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Booking could not be completed"
        )