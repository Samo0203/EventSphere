import uuid
from datetime import date, datetime, timedelta
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session
from app.agents.agents import money  # noqa: F401  (agents module registers all agents)
from app.agents.bus import AgentBus
from app.database import get_db
from app.models import Booking, Event, TicketCategory, Venue
from app.schemas import CategoryIn, CategoryOut, EventIn
from app.security import optional_user, roles

router = APIRouter(prefix="/events", tags=["Events"])


def event_dict(db, e, with_categories=False):
    cats = db.query(TicketCategory).filter_by(event_id=e.id).order_by(TicketCategory.id).all()
    v = e.venue
    d = {"id": e.id, "title": e.title, "category": e.category, "description": e.description, "venue_id": e.venue_id,
         "venue_name": v.name, "venue_location": v.location, "image_url": v.image_url, "organiser_id": e.organiser_id,
         "start_time": e.start_time.isoformat(), "end_time": e.end_time.isoformat(), "capacity": e.capacity,
         "status": e.status, "min_price": str(min((c.price for c in cats), default=0)),
         "tickets_left": sum(c.available_quantity for c in cats), "tickets_total": sum(c.total_quantity for c in cats)}
    if with_categories:
        d["categories"] = [{"id": c.id, "name": c.name, "price": str(c.price), "total_quantity": c.total_quantity,
                            "available_quantity": c.available_quantity} for c in cats]
    return d


def _check_slot(db, venue_id, start, end, exclude_event_id=None):
    r = AgentBus(db).call("EventsAPI", "VenueAgent", "REQUEST",
                          {"action": "check_slot", "venue_id": venue_id, "start": start.isoformat(),
                           "end": end.isoformat(), "exclude_event_id": exclude_event_id})
    if r["performative"] == "FAILURE":
        raise HTTPException(500, r["content"].get("reason"))
    if r["performative"] != "AGREE":
        raise HTTPException(409, r["content"]["reason"])


@router.post("/", status_code=201)
def create(data: EventIn, db: Session = Depends(get_db), u=Depends(roles("admin"))):
    venue = db.query(Venue).filter_by(id=data.venue_id, is_available=True).first()
    if not venue:
        raise HTTPException(404, "Venue not available")
    if data.capacity > venue.capacity:
        raise HTTPException(400, f"Event capacity exceeds venue capacity ({venue.capacity})")
    if data.status == "published" and not data.categories:
        raise HTTPException(400, "Add at least one ticket category before publishing")
    _check_slot(db, data.venue_id, data.start_time, data.end_time)
    e = Event(title=data.title, category=data.category, description=data.description, venue_id=data.venue_id,
              organiser_id=u.id, start_time=data.start_time, end_time=data.end_time, capacity=data.capacity,
              status=data.status)
    db.add(e)
    db.flush()
    for c in data.categories:
        db.add(TicketCategory(event_id=e.id, name=c.name, price=c.price, total_quantity=c.total_quantity,
                              available_quantity=c.total_quantity))
    db.commit()
    db.refresh(e)
    return event_dict(db, e, True)


@router.get("/manage")
def manage_list(db: Session = Depends(get_db), u=Depends(roles("admin"))):
    return [event_dict(db, e, True) for e in db.query(Event).order_by(Event.start_time.desc()).all()]


@router.get("/")
def list_events(q: Optional[str] = None, category: Optional[str] = None, venue_id: Optional[int] = None,
                date_from: Optional[date] = None, date_to: Optional[date] = None,
                min_price: Optional[float] = None, max_price: Optional[float] = None,
                db: Session = Depends(get_db)):
    query = db.query(Event).filter(Event.status == "published")
    if q:
        query = query.filter(Event.title.ilike(f"%{q}%") | Event.description.ilike(f"%{q}%"))
    if category:
        query = query.filter(Event.category == category)
    if venue_id:
        query = query.filter(Event.venue_id == venue_id)
    if date_from:
        query = query.filter(Event.start_time >= datetime.combine(date_from, datetime.min.time()))
    if date_to:
        query = query.filter(Event.start_time < datetime.combine(date_to, datetime.min.time()) + timedelta(days=1))
    rows = [event_dict(db, e) for e in query.order_by(Event.start_time).all()]
    if min_price is not None:
        rows = [r for r in rows if float(r["min_price"]) >= min_price]
    if max_price is not None:
        rows = [r for r in rows if float(r["min_price"]) <= max_price]
    return rows


@router.get("/{eid}")
def get_event(eid: int, db: Session = Depends(get_db), user=Depends(optional_user)):
    e = db.query(Event).filter_by(id=eid).first()
    if not e or (e.status == "draft" and not (user and user.role == "admin")):
        raise HTTPException(404, "Event not found")
    return event_dict(db, e, True)


@router.put("/{eid}")
def update(eid: int, data: EventIn, db: Session = Depends(get_db), u=Depends(roles("admin"))):
    e = db.query(Event).filter_by(id=eid).first()
    if not e:
        raise HTTPException(404, "Event not found")
    if e.status == "cancelled":
        raise HTTPException(400, "A cancelled event cannot be edited")
    venue = db.query(Venue).filter_by(id=data.venue_id, is_available=True).first()
    if not venue:
        raise HTTPException(404, "Venue not available")
    if data.capacity > venue.capacity:
        raise HTTPException(400, f"Event capacity exceeds venue capacity ({venue.capacity})")
    total = db.query(func.coalesce(func.sum(TicketCategory.total_quantity), 0)).filter_by(event_id=eid).scalar()
    if total > data.capacity:
        raise HTTPException(400, "Existing ticket quantities exceed the new capacity")
    _check_slot(db, data.venue_id, data.start_time, data.end_time, exclude_event_id=eid)
    for k in ("title", "category", "description", "venue_id", "start_time", "end_time", "capacity"):
        setattr(e, k, getattr(data, k))
    db.commit()
    return event_dict(db, e, True)


@router.put("/{eid}/publish")
def publish(eid: int, db: Session = Depends(get_db), u=Depends(roles("admin"))):
    e = db.query(Event).filter_by(id=eid).first()
    if not e:
        raise HTTPException(404, "Event not found")
    if e.status == "cancelled":
        raise HTTPException(400, "A cancelled event cannot be published")
    cats = db.query(TicketCategory).filter_by(event_id=eid).all()
    if not cats:
        raise HTTPException(400, "Add at least one ticket category before publishing")
    if sum(c.total_quantity for c in cats) > e.capacity:
        raise HTTPException(400, "Ticket inventory exceeds event capacity")
    e.status = "published"
    db.commit()
    return {"status": "published"}


@router.post("/{eid}/categories", response_model=CategoryOut, status_code=201)
def add_category(eid: int, data: CategoryIn, db: Session = Depends(get_db), u=Depends(roles("admin"))):
    e = db.query(Event).filter_by(id=eid).first()
    if not e:
        raise HTTPException(404, "Event not found")
    if e.status == "cancelled":
        raise HTTPException(400, "A cancelled event cannot be changed")
    existing = db.query(func.coalesce(func.sum(TicketCategory.total_quantity), 0)).filter_by(event_id=eid).scalar()
    if existing + data.total_quantity > e.capacity:
        raise HTTPException(400, "Ticket quantities exceed event capacity")
    c = TicketCategory(event_id=eid, name=data.name, price=data.price, total_quantity=data.total_quantity,
                       available_quantity=data.total_quantity)
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


@router.delete("/{eid}/categories/{cid}")
def delete_category(eid: int, cid: int, db: Session = Depends(get_db), u=Depends(roles("admin"))):
    c = db.query(TicketCategory).filter_by(id=cid, event_id=eid).first()
    if not c:
        raise HTTPException(404, "Ticket category not found")
    if db.query(Booking).filter_by(ticket_category_id=cid).first():
        raise HTTPException(400, "This category already has bookings and cannot be deleted")
    db.delete(c)
    db.commit()
    return {"deleted": True}


@router.get("/{eid}/categories", response_model=list[CategoryOut])
def categories(eid: int, db: Session = Depends(get_db)):
    return db.query(TicketCategory).filter_by(event_id=eid).order_by(TicketCategory.id).all()


@router.post("/{eid}/cancel")
def cancel(eid: int, db: Session = Depends(get_db), u=Depends(roles("admin"))):
    e = db.query(Event).filter_by(id=eid).first()
    if not e:
        raise HTTPException(404, "Event not found")
    if e.status == "cancelled":
        raise HTTPException(400, "Event is already cancelled")
    e.status = "cancelled"
    db.flush()
    r = AgentBus(db).call("EventsAPI", "BookingAgent", "REQUEST", {"action": "cancel_event", "event_id": eid}, str(uuid.uuid4()))
    if r["performative"] != "AGREE":
        db.rollback()
        raise HTTPException(500, r["content"].get("reason", "Could not cancel event"))
    return {"status": "cancelled", **r["content"],
            "refund_policy": "Every confirmed booking was refunded in full (simulated) and its tickets were voided."}
