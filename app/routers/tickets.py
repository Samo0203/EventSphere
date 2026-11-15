import io
import qrcode
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from app.agents import agents  # noqa: F401
from app.agents.bus import AgentBus
from app.database import get_db
from app.models import Booking, Ticket
from app.schemas import CheckInIn
from app.security import current_user, roles

router = APIRouter(prefix="/tickets", tags=["Digital Tickets"])


@router.get("/mine")
def my_tickets(db: Session = Depends(get_db), u=Depends(current_user)):
    rows = db.query(Ticket).join(Booking).filter(Booking.user_id == u.id).all()
    return [{"id": t.id, "booking_id": t.booking_id, "event": t.booking.event.title, "event_id": t.booking.event_id,
             "qr_code": t.qr_code, "status": t.status, "checked_in": t.checked_in} for t in rows]


@router.get("/{ticket_id}/qr")
def qr_image(ticket_id: int, db: Session = Depends(get_db), u=Depends(current_user)):
    t = db.query(Ticket).join(Booking).filter(Ticket.id == ticket_id, Booking.user_id == u.id).first()
    if not t:
        raise HTTPException(404, "Ticket not found")
    buf = io.BytesIO()
    qrcode.make(t.qr_code).save(buf, format="PNG")
    buf.seek(0)
    return StreamingResponse(buf, media_type="image/png")


@router.post("/check-in")
def check_in(data: CheckInIn, db: Session = Depends(get_db), staff=Depends(roles("admin", "staff"))):
    r = AgentBus(db).call("ScannerAPI", "TicketAgent", "REQUEST",
                          {"action": "check_in", "qr_code": data.qr_code, "event_id": data.event_id})
    if r["performative"] == "FAILURE":
        raise HTTPException(500, r["content"].get("reason", "Check-in failed"))
    c = r["content"]
    return {"admitted": bool(c.get("admitted")), "reason": c.get("reason", ""), "detail": c.get("detail"),
            "ticket_id": c.get("ticket_id"), "holder": c.get("holder")}