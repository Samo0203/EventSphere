import os
os.environ["DATABASE_URL"] = "sqlite://"
os.environ["SECRET_KEY"] = "test-secret-key-long-enough-for-tests"
os.environ["SEED_DEMO"] = "0"
os.environ["DISABLE_WORKER"] = "1"

from datetime import timedelta
from types import SimpleNamespace
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from app.database import Base, get_db
from app.main import app
from app.models import Event, TicketCategory, User, Venue
from app.security import create_token_pair, hash_password
from app.timeutil import now_local


def hdr(user):
    """Auth + CSRF headers for a user (what the browser sends after login)."""
    token, csrf = create_token_pair(user)
    return {"Authorization": f"Bearer {token}", "X-CSRF-Token": csrf}


@pytest.fixture()
def S():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    Base.metadata.create_all(engine)
    db = Session()
    mk = lambda n, e, r: User(full_name=n, email=e, hashed_password=hash_password("password123"), role=r)
    admin, attendee, staff = mk("Admin User", "admin@test.com", "admin"), mk("Attendee", "user@test.com", "attendee"), mk("Staff", "staff@test.com", "staff")
    db.add_all([admin, attendee, staff])
    db.commit()
    venue = Venue(name="Test Hall", location="Campus", capacity=100, price_per_hour=1000, is_available=True, open_for_hire=True)
    db.add(venue)
    db.commit()
    start = now_local() + timedelta(days=5)
    event = Event(title="Test Event", category="Workshop", venue_id=venue.id, organiser_id=admin.id, start_time=start,
                  end_time=start + timedelta(hours=2), capacity=50, status="published")
    db.add(event)
    db.commit()
    cat = TicketCategory(event_id=event.id, name="Standard", price=100, total_quantity=2, available_quantity=2)
    db.add(cat)
    db.commit()

    def override():
        db.expire_all()  # each request starts from fresh DB state, like a real per-request session
        try:
            yield db
        finally:
            pass
    app.dependency_overrides[get_db] = override
    with TestClient(app) as client:
        yield SimpleNamespace(c=client, db=db, admin=admin, attendee=attendee, staff=staff, venue=venue, event=event, cat=cat)
    app.dependency_overrides.clear()
    db.close()
    Base.metadata.drop_all(engine)
