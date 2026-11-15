from datetime import timedelta
from fastapi import APIRouter,Depends,HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Event,Venue,TicketCategory
from app.schemas import EventIn,EventOut,CategoryIn,CategoryOut
from app.security import current_user,roles
from app.agents.agents import VenueAgent
router=APIRouter(prefix="/events",tags=["Events"])

@router.post("/",response_model=EventOut,status_code=201)
def create(data:EventIn,db:Session=Depends(get_db),u=Depends(roles("admin"))):
    venue=db.query(Venue).filter_by(id=data.venue_id,is_available=True).first()
    if not venue: raise HTTPException(404,"Venue not available")
    if data.capacity>venue.capacity: raise HTTPException(400,"Event capacity exceeds venue capacity")
    decision=VenueAgent(db).check_slot(data.venue_id,data.start_time,data.end_time)
    if decision["decision"]!="AGREE": raise HTTPException(409,decision["reason"])
    e=Event(**data.model_dump(),organiser_id=u.id); db.add(e); db.commit(); db.refresh(e); return e

@router.get("/",response_model=list[EventOut])
def list_events(q:str|None=None,category:str|None=None,db:Session=Depends(get_db)):
    query=db.query(Event).filter(Event.status=="published")
    if q: query=query.filter(Event.title.ilike(f"%{q}%")|Event.description.ilike(f"%{q}%"))
    if category: query=query.filter(Event.category==category)
    return query.order_by(Event.start_time).all()

@router.get("/{eid}",response_model=EventOut)
def get_event(eid:int,db:Session=Depends(get_db)):
    e=db.query(Event).filter_by(id=eid).first()
    if not e: raise HTTPException(404,"Event not found")
    return e

@router.put("/{eid}/publish")
def publish(eid:int,db:Session=Depends(get_db),u=Depends(roles("admin"))):
    e=db.query(Event).filter_by(id=eid).first()
    if not e: raise HTTPException(404,"Event not found")
    cats=db.query(TicketCategory).filter_by(event_id=eid).all()
    if not cats: raise HTTPException(400,"Add at least one ticket category before publishing")
    if sum(c.total_quantity for c in cats)>e.capacity: raise HTTPException(400,"Ticket inventory exceeds event capacity")
    e.status="published"; db.commit(); return {"status":"published"}

@router.post("/{eid}/categories",response_model=CategoryOut,status_code=201)
def add_category(eid:int,data:CategoryIn,db:Session=Depends(get_db),u=Depends(roles("admin"))):
    e=db.query(Event).filter_by(id=eid).first()
    if not e: raise HTTPException(404,"Event not found")
    existing=sum(c.total_quantity for c in db.query(TicketCategory).filter_by(event_id=eid).all())
    if existing+data.total_quantity>e.capacity: raise HTTPException(400,"Ticket quantities exceed event capacity")
    c=TicketCategory(event_id=eid,name=data.name,price=data.price,total_quantity=data.total_quantity,available_quantity=data.total_quantity)
    db.add(c); db.commit(); db.refresh(c); return c

@router.get("/{eid}/categories",response_model=list[CategoryOut])
def categories(eid:int,db:Session=Depends(get_db)):
    return db.query(TicketCategory).filter_by(event_id=eid).all()

@router.post("/{eid}/cancel")
def cancel(eid:int,db:Session=Depends(get_db),u=Depends(roles("admin"))):
    e=db.query(Event).filter_by(id=eid).first()
    if not e: raise HTTPException(404,"Event not found")
    e.status="cancelled"
    for b in e.__dict__.get("bookings",[]): pass
    db.commit(); return {"status":"cancelled","refund_policy":"Full simulated refunds are recorded for cancelled events; contact admin for processing."}
