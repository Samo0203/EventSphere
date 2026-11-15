from datetime import datetime
from decimal import Decimal
from typing import Optional
from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator

class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)

class RegisterIn(BaseModel):
    full_name: str = Field(min_length=2, max_length=150)
    email: EmailStr
    password: str = Field(min_length=8)

class UserOut(ORMModel):
    id: int
    full_name: str
    email: EmailStr
    role: str

class VenueIn(BaseModel):
    name: str
    location: str
    capacity: int = Field(gt=0)
    description: Optional[str] = None
    image_url: Optional[str] = None
    price_per_hour: Decimal = Field(ge=0)
    is_available: bool = True

class VenueOut(ORMModel):
    id: int
    name: str
    location: str
    capacity: int
    description: Optional[str]
    image_url: Optional[str]
    price_per_hour: Decimal
    is_available: bool

class EventIn(BaseModel):
    title: str
    category: str = "Other"
    description: Optional[str] = None
    venue_id: int = Field(gt=0)
    start_time: datetime
    end_time: datetime
    capacity: int = Field(gt=0)
    status: str = "draft"

    @model_validator(mode="after")
    def times_valid(self):
        if self.end_time <= self.start_time:
            raise ValueError("End time must be after start time")
        if self.status not in ("draft", "published"):
            raise ValueError("Status must be draft or published")
        return self

class EventOut(ORMModel):
    id: int
    title: str
    category: str
    description: Optional[str]
    venue_id: int
    organiser_id: int
    start_time: datetime
    end_time: datetime
    capacity: int
    status: str

class CategoryIn(BaseModel):
    name: str
    price: Decimal = Field(ge=0)
    total_quantity: int = Field(gt=0)

class CategoryOut(ORMModel):
    id: int
    event_id: int
    name: str
    price: Decimal
    total_quantity: int
    available_quantity: int

class BookingIn(BaseModel):
    event_id: int
    ticket_category_id: int
    quantity: int = Field(gt=0, le=6)

class TicketOut(ORMModel):
    id: int
    booking_id: int
    qr_code: str
    status: str
    checked_in: bool
    checked_in_at: Optional[datetime]

class CheckInIn(BaseModel):
    qr_code: str
    event_id: int

class HireIn(BaseModel):
    venue_id: int
    event_date: datetime
    start_time: datetime
    end_time: datetime
    purpose: str
    guest_count: int = Field(gt=0)

    @model_validator(mode="after")
    def valid_times(self):
        if self.end_time <= self.start_time:
            raise ValueError("End time must be after start time")
        return self

class WaitlistIn(BaseModel):
    event_id: int
    ticket_category_id: int
    quantity: int = Field(gt=0, le=6)
