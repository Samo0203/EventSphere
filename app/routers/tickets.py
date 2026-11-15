import io, base64
import qrcode
from fastapi import APIRouter,Depends,HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Ticket,Booking
from app.schemas import CheckInIn
from app.security import current_user,roles
from app.agents.agents import TicketAgent
router=APIRouter(prefix="/tickets",tags=["Digital Tickets"])

@router.get("/mine")
def my_tickets(db:Session=Depends(get_db),u=Depends(current_user)):
    rows=db.query(Ticket).join(Booking).filter(Booking.user_id==u.id).all()
    return [{"id":t.id,"booking_id":t.booking_id,"event":t.booking.event.title,"event_id":t.booking.event_id,"qr_code":t.qr_code,"status":t.status,"checked_in":t.checked_in} for t in rows]

@router.get("/{ticket_id}/qr")
def qr_image(ticket_id:int,db:Session=Depends(get_db),u=Depends(current_user)):
    t=db.query(Ticket).join(Booking).filter(Ticket.id==ticket_id,Booking.user_id==u.id).first()
    if not t: raise HTTPException(404,"Ticket not found")
    img=qrcode.make(t.qr_code); buf=io.BytesIO(); img.save(buf,format="PNG"); buf.seek(0)
    return StreamingResponse(buf,media_type="image/png")

@router.post("/check-in")
def check_in(data:CheckInIn,db:Session=Depends(get_db),staff=Depends(roles("admin","staff"))):
    return TicketAgent(db).check_in(data.qr_code,data.event_id)
