import secrets
from fastapi import APIRouter,Depends,HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Booking,Event,TicketCategory,Payment,Ticket,WaitlistEntry
from app.schemas import BookingIn,TicketOut
from app.security import current_user
from app.agents.agents import BookingAgent,TicketAgent,WaitlistAgent,NotificationAgent
from app.agents.bus import AgentBus
router=APIRouter(prefix="/bookings",tags=["Bookings"])

@router.post("/",status_code=201)
def book(data:BookingIn,db:Session=Depends(get_db),u=Depends(current_user)):
    event=db.query(Event).filter_by(id=data.event_id,status="published").first()
    if not event: raise HTTPException(404,"Published event not found")
    cat=db.query(TicketCategory).filter_by(id=data.ticket_category_id,event_id=data.event_id).first()
    if not cat: raise HTTPException(404,"Ticket category not found")
    agent=BookingAgent(db); verdict=agent.assess(cat,data.quantity)
    if verdict["decision"]!="AGREE": raise HTTPException(400,verdict["reason"])
    # Conditional SQL UPDATE is atomic: concurrent requests cannot decrement below zero.
    changed=db.query(TicketCategory).filter(TicketCategory.id==cat.id,TicketCategory.available_quantity>=data.quantity).update(
        {TicketCategory.available_quantity:TicketCategory.available_quantity-data.quantity},synchronize_session=False)
    if changed!=1: db.rollback(); raise HTTPException(409,"Tickets sold out; join the waitlist")
    try:
        total=cat.price*data.quantity
        b=Booking(user_id=u.id,event_id=event.id,ticket_category_id=cat.id,quantity=data.quantity,total_amount=total,status="confirmed")
        db.add(b); db.flush()
        ref="SIM-"+secrets.token_hex(8).upper()
        db.add(Payment(booking_id=b.id,payment_reference=ref,amount=total,status="success"))
        db.flush()
        tickets=TicketAgent(db).issue(b)
        AgentBus(db).send("BookingAgent","TicketAgent","REQUEST",{"booking_id":b.id,"quantity":data.quantity})
        NotificationAgent(db).notify(u.id,"Booking confirmed",f"Your booking #{b.id} is confirmed. Simulated payment reference: {ref}")
        db.commit()
        return {"booking_id":b.id,"event":event.title,"quantity":b.quantity,"amount":str(total),"payment_reference":ref,"tickets":[{"id":t.id,"qr_code":t.qr_code} for t in tickets]}
    except Exception:
        db.rollback(); raise

@router.get("/mine")
def mine(db:Session=Depends(get_db),u=Depends(current_user)):
    rows=db.query(Booking).filter_by(user_id=u.id).order_by(Booking.created_at.desc()).all()
    return [{"id":b.id,"event":b.event.title,"event_id":b.event_id,"quantity":b.quantity,"amount":str(b.total_amount),"status":b.status,
             "tickets":[{"id":t.id,"qr_code":t.qr_code,"checked_in":t.checked_in} for t in db.query(Ticket).filter_by(booking_id=b.id).all()]} for b in rows]

@router.post("/{bid}/cancel")
def cancel_booking(bid:int,db:Session=Depends(get_db),u=Depends(current_user)):
    b=db.query(Booking).filter_by(id=bid,user_id=u.id).first()
    if not b: raise HTTPException(404,"Booking not found")
    if b.status!="confirmed": raise HTTPException(400,"Booking is not active")
    refund=BookingAgent(db).refund(b,b.event)
    b.status="cancelled"
    for t in db.query(Ticket).filter_by(booking_id=bid).all(): t.status="cancelled"
    cat=db.query(TicketCategory).filter_by(id=b.ticket_category_id).first()
    cat.available_quantity=min(cat.total_quantity,cat.available_quantity+b.quantity)
    for p in db.query(Payment).filter_by(booking_id=bid).all(): p.status="refunded" if refund>0 else "no_refund"
    db.commit()
    if refund>0: WaitlistAgent(db).offer_next(b.event_id,b.ticket_category_id,cat.available_quantity)
    return {"status":"cancelled","refund_amount":str(refund),"policy":"100% refund at least 48 hours before event; no refund inside 48 hours; full refund if event cancelled."}
