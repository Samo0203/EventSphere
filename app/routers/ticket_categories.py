from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Event, TicketCategory
from app.schemas import TicketCategoryCreate, TicketCategoryResponse
from app.security import get_current_user, require_roles

router = APIRouter(
    prefix="/ticket-categories",
    tags=["Ticket Categories"]
)


def check_event_ownership(db, event_id, current_user):
    event = db.query(Event).filter(Event.id == event_id).first()

    if not event:
        raise HTTPException(
            status_code=404,
            detail="Event not found"
        )

    if current_user.role != "admin" and event.organiser_id != current_user.id:
        raise HTTPException(
            status_code=403,
            detail="You can only manage ticket categories for your own events"
        )

    return event


@router.post(
    "/",
    response_model=TicketCategoryResponse,
    status_code=status.HTTP_201_CREATED
)
def create_ticket_category(
    category_data: TicketCategoryCreate,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("admin", "organiser"))
):
    check_event_ownership(db, category_data.event_id, current_user)

    if category_data.total_quantity <= 0:
        raise HTTPException(
            status_code=400,
            detail="Ticket quantity must be greater than zero"
        )

    if category_data.price < 0:
        raise HTTPException(
            status_code=400,
            detail="Ticket price cannot be negative"
        )

    new_category = TicketCategory(
        event_id=category_data.event_id,
        name=category_data.name,
        price=category_data.price,
        total_quantity=category_data.total_quantity,
        available_quantity=category_data.total_quantity
    )

    db.add(new_category)
    db.commit()
    db.refresh(new_category)

    return new_category


@router.get(
    "/event/{event_id}",
    response_model=list[TicketCategoryResponse]
)
def get_event_ticket_categories(
    event_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    event = db.query(Event).filter(Event.id == event_id).first()

    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    return db.query(TicketCategory).filter(
        TicketCategory.event_id == event_id
    ).all()


@router.get(
    "/{category_id}",
    response_model=TicketCategoryResponse
)
def get_ticket_category(
    category_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    category = db.query(TicketCategory).filter(
        TicketCategory.id == category_id
    ).first()

    if not category:
        raise HTTPException(status_code=404, detail="Ticket category not found")

    return category


@router.put(
    "/{category_id}",
    response_model=TicketCategoryResponse
)
def update_ticket_category(
    category_id: int,
    category_data: TicketCategoryCreate,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("admin", "organiser"))
):
    category = db.query(TicketCategory).filter(
        TicketCategory.id == category_id
    ).first()

    if not category:
        raise HTTPException(status_code=404, detail="Ticket category not found")

    check_event_ownership(db, category.event_id, current_user)

    if category_data.event_id != category.event_id:
        raise HTTPException(
            status_code=400,
            detail="You cannot move a ticket category to another event"
        )

    if category_data.total_quantity < category.total_quantity - (
        category.total_quantity - category.available_quantity
    ):
        raise HTTPException(
            status_code=400,
            detail="New quantity cannot be less than tickets already sold"
        )

    if category_data.price < 0:
        raise HTTPException(status_code=400, detail="Ticket price cannot be negative")

    sold_quantity = category.total_quantity - category.available_quantity

    category.name = category_data.name
    category.price = category_data.price
    category.total_quantity = category_data.total_quantity
    category.available_quantity = category_data.total_quantity - sold_quantity

    db.commit()
    db.refresh(category)

    return category


@router.delete("/{category_id}")
def delete_ticket_category(
    category_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("admin", "organiser"))
):
    category = db.query(TicketCategory).filter(
        TicketCategory.id == category_id
    ).first()

    if not category:
        raise HTTPException(status_code=404, detail="Ticket category not found")

    check_event_ownership(db, category.event_id, current_user)

    if category.available_quantity != category.total_quantity:
        raise HTTPException(
            status_code=400,
            detail="Cannot delete a category after tickets have been sold"
        )

    db.delete(category)
    db.commit()

    return {"message": "Ticket category deleted successfully"}