from datetime import datetime
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, Numeric, String, Text, Index
from sqlalchemy.orm import relationship
from app.database import Base

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    full_name = Column(String(150), nullable=False)
    email = Column(String(255), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    role = Column(String(20), nullable=False, default="attendee")  # admin, staff, attendee
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

class Venue(Base):
    __tablename__ = "venues"
    id = Column(Integer, primary_key=True)
    name = Column(String(150), nullable=False)
    location = Column(String(255), nullable=False)
    capacity = Column(Integer, nullable=False)
    description = Column(Text)
    image_url = Column(String(500))
    price_per_hour = Column(Numeric(10,2), nullable=False, default=0)
    is_available = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

class Event(Base):
    __tablename__ = "events"
    id = Column(Integer, primary_key=True)
    title = Column(String(200), nullable=False)
    category = Column(String(80), nullable=False, default="Other")
    description = Column(Text)
    venue_id = Column(Integer, ForeignKey("venues.id"), nullable=False)
    organiser_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    start_time = Column(DateTime, nullable=False)
    end_time = Column(DateTime, nullable=False)
    capacity = Column(Integer, nullable=False)
    status = Column(String(20), nullable=False, default="draft")  # draft/published/cancelled
    created_at = Column(DateTime, default=datetime.utcnow)
    venue = relationship("Venue")
    organiser = relationship("User")

class TicketCategory(Base):
    __tablename__ = "ticket_categories"
    id = Column(Integer, primary_key=True)
    event_id = Column(Integer, ForeignKey("events.id"), nullable=False, index=True)
    name = Column(String(100), nullable=False)
    price = Column(Numeric(10,2), nullable=False)
    total_quantity = Column(Integer, nullable=False)
    available_quantity = Column(Integer, nullable=False)

class Booking(Base):
    __tablename__ = "bookings"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    event_id = Column(Integer, ForeignKey("events.id"), nullable=False, index=True)
    ticket_category_id = Column(Integer, ForeignKey("ticket_categories.id"), nullable=False)
    quantity = Column(Integer, nullable=False)
    total_amount = Column(Numeric(10,2), nullable=False)
    status = Column(String(20), nullable=False, default="confirmed")
    created_at = Column(DateTime, default=datetime.utcnow)
    user = relationship("User")
    event = relationship("Event")
    ticket_category = relationship("TicketCategory")

class Ticket(Base):
    __tablename__ = "tickets"
    id = Column(Integer, primary_key=True)
    booking_id = Column(Integer, ForeignKey("bookings.id"), nullable=False, index=True)
    qr_code = Column(String(100), unique=True, nullable=False, index=True)
    status = Column(String(20), nullable=False, default="valid")
    checked_in = Column(Boolean, nullable=False, default=False)
    checked_in_at = Column(DateTime)
    booking = relationship("Booking")

class Payment(Base):
    __tablename__ = "payments"
    id = Column(Integer, primary_key=True)
    booking_id = Column(Integer, ForeignKey("bookings.id"), nullable=False, index=True)
    payment_reference = Column(String(100), unique=True, nullable=False)
    amount = Column(Numeric(10,2), nullable=False)
    status = Column(String(20), nullable=False, default="success")
    created_at = Column(DateTime, default=datetime.utcnow)

class AgentMessage(Base):
    __tablename__ = "agent_messages"
    id = Column(Integer, primary_key=True)
    sender = Column(String(60), nullable=False)
    receiver = Column(String(60), nullable=False)
    performative = Column(String(20), nullable=False)
    content = Column(Text, nullable=False)
    conversation_id = Column(String(80), nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)

class AgentState(Base):
    __tablename__ = "agent_states"
    id = Column(Integer, primary_key=True)
    agent_name = Column(String(60), unique=True, nullable=False)
    state_json = Column(Text, nullable=False, default="{}")
    updated_at = Column(DateTime, default=datetime.utcnow)

class VenueHire(Base):
    __tablename__ = "venue_hires"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    venue_id = Column(Integer, ForeignKey("venues.id"), nullable=False)
    event_date = Column(DateTime, nullable=False)
    start_time = Column(DateTime, nullable=False)
    end_time = Column(DateTime, nullable=False)
    purpose = Column(Text)
    guest_count = Column(Integer, nullable=False)
    quoted_price = Column(Numeric(10,2), nullable=False, default=0)
    status = Column(String(20), nullable=False, default="pending")
    decision_reason = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)

class WaitlistEntry(Base):
    __tablename__ = "waitlist_entries"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    event_id = Column(Integer, ForeignKey("events.id"), nullable=False)
    ticket_category_id = Column(Integer, ForeignKey("ticket_categories.id"), nullable=False)
    quantity = Column(Integer, nullable=False, default=1)
    status = Column(String(20), nullable=False, default="waiting")
    offered_at = Column(DateTime)
    expires_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)

class Notification(Base):
    __tablename__ = "notifications"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    title = Column(String(200), nullable=False)
    message = Column(Text, nullable=False)
    is_read = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

Index("ix_event_venue_time", Event.venue_id, Event.start_time, Event.end_time)
