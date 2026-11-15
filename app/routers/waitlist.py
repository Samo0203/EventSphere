from fastapi import APIRouter,Depends,HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Event,TicketCategory,WaitlistEntry
from app.schemas import WaitlistIn
from app.security import current_user
from app.agents.agents import WaitlistAgent
router=APIRouter(prefix="/waitlist",tags=["Waitlist"])

@router.post("/",status_code=201)
def join(data:WaitlistIn,db:Session=Depends(get_db),u=Depends(current_user)):
    cat=db.query(TicketCategory).filter_by(id=data.ticket_category_id,event_id=data.event_id).first()
    if not cat: raise HTTPException(404,"Ticket category not found")
    if cat.available_quantity>=data.quantity: raise HTTPException(400,"Tickets are currently available; book directly")
    e=WaitlistEntry(user_id=u.id,event_id=data.event_id,ticket_category_id=cat.id,quantity=data.quantity,status="waiting")
    db.add(e); db.commit(); db.refresh(e); return {"waitlist_id":e.id,"status":e.status}
@router.get("/mine")
def mine(db:Session=Depends(get_db),u=Depends(current_user)):
    return db.query(WaitlistEntry).filter_by(user_id=u.id).order_by(WaitlistEntry.created_at.desc()).all()
