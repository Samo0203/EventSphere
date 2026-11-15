from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.agents import agents  # noqa: F401  (registers agents)
from app.agents.bus import AgentBus
from app.database import get_db
from app.models import Booking, Ticket
from app.routers.common import qr_data_uri, respond
from app.schemas import BookingIn
from app.security import current_user

router = APIRouter(prefix="/bookings", tags=["Bookings"])


@router.post("/", status_code=201)
def book(data: BookingIn, db: Session = Depends(get_db), u=Depends(current_user)):
    reply = AgentBus(db).call("BookingAPI", "BookingAgent", "REQUEST", {
        "action": "book", "user_id": u.id, "event_id": data.event_id,
        "ticket_category_id": data.ticket_category_id, "quantity": data.quantity})
    return respond(reply)


@router.get("/mine")
def mine(db: Session = Depends(get_db), u=Depends(current_user)):
    rows = db.query(Booking).filter_by(user_id=u.id).order_by(Booking.created_at.desc(), Booking.id.desc()).all()
    out = []
    for b in rows:
        tickets = db.query(Ticket).filter_by(booking_id=b.id).order_by(Ticket.id).all()
        out.append({"id": b.id, "event": b.event.title, "event_id": b.event_id, "event_start": b.event.start_time.isoformat(),
                    "venue": b.event.venue.name, "category": b.ticket_category.name, "quantity": b.quantity,
                    "amount": str(b.total_amount), "refund_amount": str(b.refund_amount or 0), "status": b.status,
                    "event_status": b.event.status,
                    "tickets": [{"id": t.id, "qr_code": t.qr_code, "status": t.status, "checked_in": t.checked_in,
                                 "qr_image": qr_data_uri(t.qr_code) if t.status == "valid" else None} for t in tickets]})
    return out


@router.post("/{bid}/cancel")
def cancel_booking(bid: int, db: Session = Depends(get_db), u=Depends(current_user)):
    return respond(AgentBus(db).call("BookingAPI", "BookingAgent", "REQUEST",
                                     {"action": "cancel", "booking_id": bid, "user_id": u.id}))
