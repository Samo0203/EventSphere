
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from datetime import timedelta

from app.database import get_db
from app.models import Event, Venue
from app.schemas import EventCreate, EventResponse
from app.security import get_current_user, require_roles

router = APIRouter(prefix="/events", tags=["Event Management"])


def check_event_details(db: Session, event_data: EventCreate, exclude_event_id=None):
    venue = db.query(Venue).filter(
        Venue.id == event_data.venue_id
    ).first()

    if not venue:
        raise HTTPException(
            status_code=404,
            detail="Venue not found"
        )

    if not venue.is_available:
        raise HTTPException(
            status_code=400,
            detail="This venue is currently unavailable"
        )

    if event_data.capacity > venue.capacity:
        raise HTTPException(
            status_code=400,
            detail=f"Event capacity cannot exceed venue capacity ({venue.capacity})"
        )

    # Check whether another event overlaps at the same venue
    buffer = timedelta(minutes=30)

    query = db.query(Event).filter(
        Event.venue_id == event_data.venue_id,
        Event.start_time < event_data.end_time + buffer,
        Event.end_time > event_data.start_time - buffer
    )

    if exclude_event_id is not None:
        query = query.filter(Event.id != exclude_event_id)

    conflicting_event = query.first()

    if conflicting_event:
        raise HTTPException(
            status_code=409,
            detail="This venue already has an event scheduled during that time"
        )

    return venue


# CREATE EVENT - ORGANISER OR ADMIN
@router.post(
    "/",
    response_model=EventResponse,
    status_code=status.HTTP_201_CREATED
)
def create_event(
    event_data: EventCreate,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("admin", "organiser"))
):
    check_event_details(db, event_data)

    new_event = Event(
        title=event_data.title,
        description=event_data.description,
        venue_id=event_data.venue_id,
        organiser_id=current_user.id,
        start_time=event_data.start_time,
        end_time=event_data.end_time,
        capacity=event_data.capacity
    )

    db.add(new_event)
    db.commit()
    db.refresh(new_event)

    return new_event


# VIEW ALL EVENTS - AUTHENTICATED USERS
@router.get("/", response_model=list[EventResponse])
def get_all_events(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    return db.query(Event).order_by(Event.start_time.asc()).all()


# VIEW ONE EVENT - AUTHENTICATED USERS
@router.get("/{event_id}", response_model=EventResponse)
def get_event(
    event_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    event = db.query(Event).filter(Event.id == event_id).first()

    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    return event


# UPDATE EVENT - OWNER OR ADMIN
@router.put("/{event_id}", response_model=EventResponse)
def update_event(
    event_id: int,
    event_data: EventCreate,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("admin", "organiser"))
):
    event = db.query(Event).filter(Event.id == event_id).first()

    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    if current_user.role != "admin" and event.organiser_id != current_user.id:
        raise HTTPException(
            status_code=403,
            detail="You can only update your own events"
        )

    check_event_details(db, event_data, exclude_event_id=event_id)

    event.title = event_data.title
    event.description = event_data.description
    event.venue_id = event_data.venue_id
    event.start_time = event_data.start_time
    event.end_time = event_data.end_time
    event.capacity = event_data.capacity

    db.commit()
    db.refresh(event)

    return event


# CANCEL EVENT - OWNER OR ADMIN
@router.delete("/{event_id}")
def cancel_event(
    event_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("admin", "organiser"))
):
    event = db.query(Event).filter(Event.id == event_id).first()

    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    if current_user.role != "admin" and event.organiser_id != current_user.id:
        raise HTTPException(
            status_code=403,
            detail="You can only cancel your own events"
        )

    # Soft cancellation preserves booking and ticket history
    event.status = "cancelled"
    db.commit()

    return {"message": "Event cancelled successfully"}
