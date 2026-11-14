
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Venue, Event
from app.schemas import VenueCreate, VenueResponse
from app.security import get_current_user, require_roles

router = APIRouter(prefix="/venues", tags=["Venue Management"])


# CREATE VENUE - ADMIN ONLY
@router.post(
    "/",
    response_model=VenueResponse,
    status_code=status.HTTP_201_CREATED
)
def create_venue(
    venue_data: VenueCreate,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("admin"))
):
    new_venue = Venue(
        name=venue_data.name,
        location=venue_data.location,
        capacity=venue_data.capacity,
        description=venue_data.description,
        price_per_hour=venue_data.price_per_hour
    )

    db.add(new_venue)
    db.commit()
    db.refresh(new_venue)

    return new_venue


# VIEW ALL VENUES - AUTHENTICATED USERS
@router.get("/", response_model=list[VenueResponse])
def get_all_venues(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    return db.query(Venue).order_by(Venue.id.desc()).all()


# VIEW ONE VENUE - AUTHENTICATED USERS
@router.get("/{venue_id}", response_model=VenueResponse)
def get_venue(
    venue_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    venue = db.query(Venue).filter(Venue.id == venue_id).first()

    if not venue:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Venue not found"
        )

    return venue


# UPDATE VENUE - ADMIN ONLY
@router.put("/{venue_id}", response_model=VenueResponse)
def update_venue(
    venue_id: int,
    venue_data: VenueCreate,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("admin"))
):
    venue = db.query(Venue).filter(Venue.id == venue_id).first()

    if not venue:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Venue not found"
        )

    venue.name = venue_data.name
    venue.location = venue_data.location
    venue.capacity = venue_data.capacity
    venue.description = venue_data.description
    venue.price_per_hour = venue_data.price_per_hour

    db.commit()
    db.refresh(venue)

    return venue


# DELETE VENUE - ADMIN ONLY
@router.delete("/{venue_id}")
def delete_venue(
    venue_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("admin"))
):
    venue = db.query(Venue).filter(Venue.id == venue_id).first()

    if not venue:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Venue not found"
        )

    # Prevent deletion if events are associated with this venue
    linked_event = db.query(Event).filter(
        Event.venue_id == venue_id
    ).first()

    if linked_event:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete venue because events are associated with it"
        )

    db.delete(venue)
    db.commit()

    return {"message": "Venue deleted successfully"}
