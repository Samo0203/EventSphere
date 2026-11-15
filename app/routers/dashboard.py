import json
from fastapi import APIRouter,Depends
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.database import get_db
from app.models import Event,Booking,Ticket,AgentMessage,Payment
from app.security import roles
router=APIRouter(prefix="/admin",tags=["Admin Dashboard"])

@router.get("/dashboard")
def dashboard(db:Session=Depends(get_db),u=Depends(roles("admin"))):
    result=[]
    for e in db.query(Event).all():
        sold=db.query(func.coalesce(func.sum(Booking.quantity),0)).filter_by(event_id=e.id,status="confirmed").scalar()
        revenue=db.query(func.coalesce(func.sum(Payment.amount),0)).join(Booking,Payment.booking_id==Booking.id).filter(Booking.event_id==e.id,Payment.status=="success").scalar()
        checked=db.query(Ticket).join(Booking).filter(Booking.event_id==e.id,Ticket.checked_in==True).count()
        result.append({"event_id":e.id,"title":e.title,"tickets_sold":int(sold),"revenue":str(revenue),"check_ins":checked,"capacity":e.capacity})
    logs=db.query(AgentMessage).order_by(AgentMessage.created_at.desc()).limit(200).all()
    return {"events":result,"agent_messages":[{"sender":m.sender,"receiver":m.receiver,"performative":m.performative,"content":json.loads(m.content),"conversation_id":m.conversation_id,"created_at":m.created_at.isoformat()} for m in logs]}
