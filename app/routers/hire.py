from fastapi import APIRouter,Depends,HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import VenueHire,Venue
from app.schemas import HireIn
from app.security import current_user,roles
from app.agents.agents import VenueAgent,NotificationAgent
from app.agents.bus import AgentBus
router=APIRouter(prefix="/venue-hire",tags=["Private Venue Hire"])

@router.post("/",status_code=201)
def request_hire(data:HireIn,db:Session=Depends(get_db),u=Depends(current_user)):
    venue=db.query(Venue).filter_by(id=data.venue_id).first()
    if not venue: raise HTTPException(404,"Venue not found")
    h=VenueHire(user_id=u.id,venue_id=data.venue_id,event_date=data.event_date,start_time=data.start_time,end_time=data.end_time,
        purpose=data.purpose,guest_count=data.guest_count,quoted_price=0,status="pending")
    db.add(h); db.flush()
    decision=VenueAgent(db).decide_hire(h)
    h.status="confirmed" if decision["decision"]=="AGREE" else "escalated"
    h.decision_reason=decision["reason"]
    if decision.get("price"): h.quoted_price=decision["price"]
    db.commit()
    AgentBus(db).send("VenueAgent","NotificationAgent","INFORM",{"user_id":u.id,"title":"Venue hire decision","message":decision["reason"]})
    NotificationAgent(db).notify(u.id,"Venue hire decision",decision["reason"])
    return {"hire_id":h.id,"status":h.status,"price":str(h.quoted_price),"decision":decision}

@router.get("/mine")
def my_hires(db:Session=Depends(get_db),u=Depends(current_user)):
    return db.query(VenueHire).filter_by(user_id=u.id).all()

@router.get("/escalated")
def escalated(db:Session=Depends(get_db),u=Depends(roles("admin"))):
    return db.query(VenueHire).filter_by(status="escalated").all()

@router.post("/{hid}/decision")
def admin_decision(hid:int,decision:str,db:Session=Depends(get_db),u=Depends(roles("admin"))):
    if decision not in ("confirmed","rejected"): raise HTTPException(400,"Decision must be confirmed or rejected")
    h=db.query(VenueHire).filter_by(id=hid,status="escalated").first()
    if not h: raise HTTPException(404,"Escalated hire not found")
    h.status=decision; h.decision_reason=f"Administrator {decision} request"; db.commit()
    NotificationAgent(db).notify(h.user_id,"Venue hire update",h.decision_reason)
    return {"status":h.status}
