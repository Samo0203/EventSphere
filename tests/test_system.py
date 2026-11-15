import json
from datetime import datetime,timedelta
from app.models import Ticket,Booking,AgentMessage,WaitlistEntry,VenueHire,Notification,AgentState,Event,Venue,TicketCategory
from app.agents.agents import VenueAgent,BookingAgent,TicketAgent,WaitlistAgent,NotificationAgent
from app.agents.bus import AgentBus

def test_attendee_registration(setup):
    c,db,*_=setup
    r=c.post("/auth/register",json={"full_name":"New User","email":"new@test.com","password":"password123"})
    assert r.status_code==201 and r.json()["role"]=="attendee"

def test_admin_role_required_for_venue_create(setup):
    c,db,admin,attendee,*_=setup
    body={"name":"New Hall","location":"Campus","capacity":20,"price_per_hour":500}
    assert c.post("/venues/",json=body,headers={"Authorization":f"Bearer {__import__('app.security',fromlist=['create_token']).create_token(attendee)}"}).status_code==403

def test_venue_creation(setup):
    c,db,admin,*_=setup
    r=c.post("/venues/",json={"name":"Second Hall","location":"Campus","capacity":80,"price_per_hour":100},headers={"Authorization":f"Bearer {__import__('app.security',fromlist=['create_token']).create_token(admin)}"})
    assert r.status_code==201

def test_event_list_only_published(setup):
    c,db,*_=setup
    assert len(c.get("/events/").json())==1

def test_overbooking_is_rejected(setup):
    c,db,admin,attendee,staff,event,cat=setup
    from app.security import create_token
    h={"Authorization":f"Bearer {create_token(attendee)}"}
    payload={"event_id":event.id,"ticket_category_id":cat.id,"quantity":2}
    assert c.post("/bookings/",json=payload,headers=h).status_code==201
    r=c.post("/bookings/",json=payload,headers=h)
    assert r.status_code in (400,409)

def test_successful_booking_issues_one_qr_per_ticket(setup):
    c,db,admin,attendee,staff,event,cat=setup
    from app.security import create_token
    r=c.post("/bookings/",json={"event_id":event.id,"ticket_category_id":cat.id,"quantity":2},headers={"Authorization":f"Bearer {create_token(attendee)}"})
    assert r.status_code==201 and len(r.json()["tickets"])==2
    assert len({t["qr_code"] for t in r.json()["tickets"]})==2

def test_double_checkin_rejected(setup):
    c,db,admin,attendee,staff,event,cat=setup
    from app.security import create_token
    b=c.post("/bookings/",json={"event_id":event.id,"ticket_category_id":cat.id,"quantity":1},headers={"Authorization":f"Bearer {create_token(attendee)}"}).json()
    # Move event window around current time for admission test
    event.start_time=datetime.utcnow()-timedelta(minutes=10);event.end_time=datetime.utcnow()+timedelta(hours=1);db.commit()
    h={"Authorization":f"Bearer {create_token(staff)}"}
    payload={"event_id":event.id,"qr_code":b["tickets"][0]["qr_code"]}
    assert c.post("/tickets/check-in",json=payload,headers=h).json()["admitted"] is True
    second=c.post("/tickets/check-in",json=payload,headers=h).json()
    assert second["admitted"] is False and second["reason"]=="Already used"

def test_venue_agent_rejects_overlap(setup):
    c,db,admin,attendee,staff,event,cat=setup
    result=VenueAgent(db).check_slot(event.venue_id,event.start_time,event.end_time)
    assert result["decision"]=="REFUSE"

def test_booking_agent_quantity_rule(setup):
    c,db,admin,attendee,staff,event,cat=setup
    assert BookingAgent(db).assess(cat,7)["decision"]=="REFUSE"

def test_ticket_agent_rejects_unknown_code(setup):
    c,db,*_=setup
    assert TicketAgent(db).check_in("not-a-real-code",1)["admitted"] is False

def test_waitlist_agent_expiry_sweep(setup):
    c,db,admin,attendee,staff,event,cat=setup
    e=WaitlistEntry(user_id=attendee.id,event_id=event.id,ticket_category_id=cat.id,quantity=1,status="offered",offered_at=datetime.utcnow()-timedelta(minutes=20),expires_at=datetime.utcnow()-timedelta(minutes=1))
    db.add(e);db.commit()
    assert WaitlistAgent(db).expire_sweep()==1
    assert e.status=="expired"

def test_notification_agent_persists_notification(setup):
    c,db,admin,attendee,staff,event,cat=setup
    NotificationAgent(db).notify(attendee.id,"Test","Hello")
    assert db.query(Notification).filter_by(user_id=attendee.id,title="Test").count()==1

def test_agent_message_has_required_envelope(setup):
    c,db,*_=setup
    m=AgentBus(db).send("VenueAgent","NotificationAgent","INFORM",{"reason":"test"},"conv-1")
    assert set(m)=={"sender","receiver","performative","content","conversation_id"}
    assert db.query(AgentMessage).filter_by(conversation_id="conv-1").count()==1
