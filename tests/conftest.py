import os
os.environ["DATABASE_URL"]="sqlite://"
os.environ["SECRET_KEY"]="test-secret-key-long-enough-for-tests"
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient
from app.database import Base,get_db
from app.main import app
from app.models import User,Venue,Event,TicketCategory
from app.security import hash_password,create_token

@pytest.fixture()
def setup():
    engine=create_engine("sqlite://",connect_args={"check_same_thread":False},poolclass=StaticPool)
    TestingSession=sessionmaker(bind=engine,autoflush=False,autocommit=False)
    Base.metadata.create_all(engine)
    db=TestingSession()
    admin=User(full_name="Admin User",email="admin@test.com",hashed_password=hash_password("password123"),role="admin")
    attendee=User(full_name="Attendee",email="user@test.com",hashed_password=hash_password("password123"),role="attendee")
    staff=User(full_name="Staff",email="staff@test.com",hashed_password=hash_password("password123"),role="staff")
    db.add_all([admin,attendee,staff]);db.commit()
    venue=Venue(name="Test Hall",location="Campus",capacity=100,price_per_hour=1000,is_available=True)
    db.add(venue);db.commit()
    from datetime import datetime,timedelta
    start=datetime.utcnow()+timedelta(days=5)
    event=Event(title="Test Event",category="Workshop",venue_id=venue.id,organiser_id=admin.id,start_time=start,end_time=start+timedelta(hours=2),capacity=50,status="published")
    db.add(event);db.commit()
    cat=TicketCategory(event_id=event.id,name="Standard",price=100,total_quantity=2,available_quantity=2)
    db.add(cat);db.commit()
    def override():
        try: yield db
        finally: pass
    app.dependency_overrides[get_db]=override
    with TestClient(app) as client:
        yield client,db,admin,attendee,staff,event,cat
    app.dependency_overrides.clear();db.close();Base.metadata.drop_all(engine)

def auth(user):
    return {"Authorization":f"Bearer {create_token(user)}"}
