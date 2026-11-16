from datetime import datetime
from decimal import Decimal
from typing import Optional
from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class RegisterIn(BaseModel):
    full_name: str = Field(min_length=2, max_length=150)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class UserOut(ORMModel):
    id: int
    full_name: str
    email: str
    role: str


class VenueIn(BaseModel):
    name: str = Field(min_length=2, max_length=150)
    location: str = Field(min_length=2, max_length=255)
    capacity: int = Field(gt=0)
    description: Optional[str] = None
    image_url: Optional[str] = None
    price_per_hour: Decimal = Field(ge=0)
    is_available: bool = True
    open_for_hire: bool = True


class VenueOut(ORMModel):
    id: int
    name: str
    location: str
    capacity: int
    description: Optional[str]
    image_url: Optional[str]
    price_per_hour: Decimal
    is_available: bool
    open_for_hire: bool


class CategoryIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    price: Decimal = Field(ge=0)
    total_quantity: int = Field(gt=0)


class CategoryOut(ORMModel):
    id: int
    event_id: int
    name: str
    price: Decimal
    total_quantity: int
    available_quantity: int


class EventIn(BaseModel):
    title: str = Field(min_length=2, max_length=200)
    category: str = "Other"
    description: Optional[str] = None
    venue_id: int = Field(gt=0)
    start_time: datetime
    end_time: datetime
    capacity: int = Field(gt=0)
    status: str = "draft"
    categories: list[CategoryIn] = Field(default_factory=list)

    @model_validator(mode="after")
    def valid(self):
        if self.end_time <= self.start_time:
            raise ValueError("End time must be after start time")
        if self.status not in ("draft", "published"):
            raise ValueError("Status must be draft or published")
        if sum(c.total_quantity for c in self.categories) > self.capacity:
            raise ValueError("Ticket quantities exceed event capacity")
        return self


class BookingIn(BaseModel):
    event_id: int
    ticket_category_id: int
    quantity: int = Field(gt=0, le=6)


class CheckInIn(BaseModel):
    qr_code: str = Field(min_length=1, max_length=200)
    event_id: int


class HireIn(BaseModel):
    venue_id: int
    start_time: datetime
    end_time: datetime
    purpose: str = Field(min_length=2, max_length=500)
    guest_count: int = Field(gt=0)
    event_date: Optional[datetime] = None

    @model_validator(mode="after")
    def valid_times(self):
        if self.end_time <= self.start_time:
            raise ValueError("End time must be after start time")
        return self


class WaitlistIn(BaseModel):
    event_id: int
    ticket_category_id: int
    quantity: int = Field(gt=0, le=6)
