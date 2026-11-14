
from datetime import datetime
from decimal import Decimal
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator


# Allows Pydantic to read SQLAlchemy model objects
class BaseSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# -------------------------
# USER SCHEMAS
# -------------------------

class UserCreate(BaseModel):
    full_name: str = Field(min_length=2, max_length=150)
    email: EmailStr
    password: str = Field(min_length=8)
    role: Literal["admin", "organiser", "gate_staff", "attendee"] = "attendee"


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserResponse(BaseSchema):
    id: int
    full_name: str
    email: EmailStr
    role: str
    is_active: bool


# -------------------------
# VENUE SCHEMAS
# -------------------------

class VenueCreate(BaseModel):
    name: str = Field(min_length=2, max_length=150)
    location: str
    capacity: int = Field(gt=0)
    description: Optional[str] = None
    price_per_hour: Decimal = Field(default=Decimal("0"), ge=0)


class VenueResponse(BaseSchema):
    id: int
    name: str
    location: str
    capacity: int
    description: Optional[str]
    price_per_hour: Decimal
    is_available: bool


# -------------------------
# EVENT SCHEMAS
# -------------------------

class EventCreate(BaseModel):
    title: str = Field(min_length=2, max_length=200)
    description: Optional[str] = None
    venue_id: int = Field(gt=0)
    start_time: datetime
    end_time: datetime
    capacity: int = Field(gt=0)

    @model_validator(mode="after")
    def validate_event_times(self):
        if self.end_time <= self.start_time:
            raise ValueError("Event end time must be after start time")
        return self


class EventResponse(BaseSchema):
    id: int
    title: str
    description: Optional[str]
    venue_id: int
    organiser_id: int
    start_time: datetime
    end_time: datetime
    capacity: int
    status: str


# -------------------------
# TICKET CATEGORY SCHEMAS
# -------------------------

class TicketCategoryCreate(BaseModel):
    event_id: int = Field(gt=0)
    name: str
    price: Decimal = Field(ge=0)
    total_quantity: int = Field(gt=0)


class TicketCategoryResponse(BaseSchema):
    id: int
    event_id: int
    name: str
    price: Decimal
    total_quantity: int
    available_quantity: int


# -------------------------
# BOOKING SCHEMAS
# -------------------------

class BookingCreate(BaseModel):
    event_id: int = Field(gt=0)
    ticket_category_id: int = Field(gt=0)
    quantity: int = Field(gt=0)


class BookingResponse(BaseSchema):
    id: int
    user_id: int
    event_id: int
    quantity: int
    total_amount: Decimal
    status: str
    created_at: datetime


# -------------------------
# TICKET SCHEMAS
# -------------------------

class TicketResponse(BaseSchema):
    id: int
    booking_id: int
    qr_code: str
    status: str
    checked_in: bool
    checked_in_at: Optional[datetime]


# -------------------------
# PAYMENT SCHEMAS
# -------------------------

class PaymentResponse(BaseSchema):
    id: int
    booking_id: int
    payment_reference: str
    amount: Decimal
    status: str
    created_at: datetime


# -------------------------
# PRIVATE VENUE HIRE SCHEMAS
# -------------------------

class VenueHireCreate(BaseModel):
    venue_id: int = Field(gt=0)
    event_date: datetime
    start_time: datetime
    end_time: datetime
    purpose: Optional[str] = None

    @model_validator(mode="after")
    def validate_hire_times(self):
        if self.end_time <= self.start_time:
            raise ValueError("Hire end time must be after start time")
        return self


class VenueHireResponse(BaseSchema):
    id: int
    user_id: int
    venue_id: int
    event_date: datetime
    start_time: datetime
    end_time: datetime
    purpose: Optional[str]
    status: str
    decision_reason: Optional[str]


# -------------------------
# WAITLIST SCHEMAS
# -------------------------

class WaitlistCreate(BaseModel):
    event_id: int = Field(gt=0)
    quantity: int = Field(default=1, gt=0)


class WaitlistResponse(BaseSchema):
    id: int
    user_id: int
    event_id: int
    quantity: int
    status: str
    offered_at: Optional[datetime]
    expires_at: Optional[datetime]


# -------------------------
# NOTIFICATION SCHEMAS
# -------------------------

class NotificationResponse(BaseSchema):
    id: int
    user_id: int
    title: str
    message: str
    is_read: bool
    created_at: datetime
