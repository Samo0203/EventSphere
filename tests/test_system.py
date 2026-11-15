"""EventSphere test-suite: accounts, roles, CSRF, events, booking, concurrency, check-in, hire,
waitlist, refunds and every agent's decision rules (agents are driven through bus messages)."""
import json
from datetime import timedelta
from app.agents.agents import BookingAgent, NotificationAgent, TicketAgent, VenueAgent, WaitlistAgent
from app.agents.bus import AgentBus
from app.models import (AgentMessage, AgentState, Booking, Event, Notification, Payment, Ticket, TicketCategory,
                        User, VenueHire, WaitlistEntry)
from app.security import hash_password
from app.timeutil import now_local
from tests.conftest import hdr


def book(S, user=None, qty=1, cat=None):
    cat = cat or S.cat
    return S.c.post("/bookings/", json={"event_id": S.event.id, "ticket_category_id": cat.id, "quantity": qty}, headers=hdr(user or S.attendee))


def ask(S, agent, content, perf="REQUEST", cid=None):
    S.db.expire_all()
    return AgentBus(S.db).call("Test", agent, perf, content, cid)


def open_window(S):
    S.event.start_time, S.event.end_time = now_local() - timedelta(minutes=10), now_local() + timedelta(hours=1)
    S.db.commit()


# ------------------------------------------------------------------ accounts & security
def test_registration_hashes_password_and_forces_attendee(S):
    r = S.c.post("/auth/register", json={"full_name": "New User", "email": "new@test.com", "password": "password123"})
    assert r.status_code == 201 and r.json()["role"] == "attendee"
    u = S.db.query(User).filter_by(email="new@test.com").first()
    assert u.hashed_password != "password123" and u.hashed_password.startswith("$argon2")


def test_login_returns_token_and_csrf(S):
    r = S.c.post("/auth/login", data={"username": "user@test.com", "password": "password123"})
    assert r.status_code == 200 and r.json()["access_token"] and r.json()["csrf_token"]
    assert S.c.post("/auth/login", data={"username": "user@test.com", "password": "wrong"}).status_code == 401


def test_role_protection(S):
    body = {"name": "New Hall", "location": "Campus", "capacity": 20, "price_per_hour": 500}
    assert S.c.post("/venues/", json=body, headers=hdr(S.attendee)).status_code == 403
    assert S.c.get("/admin/dashboard", headers=hdr(S.staff)).status_code == 403
    assert S.c.post("/tickets/check-in", json={"qr_code": "x", "event_id": 1}, headers=hdr(S.attendee)).status_code == 403
    assert S.c.get("/admin/dashboard").status_code == 401


def test_csrf_token_required_for_state_changes(S):
    token_only = {"Authorization": hdr(S.admin)["Authorization"]}
    body = {"name": "CSRF Hall", "location": "Campus", "capacity": 20, "price_per_hour": 500}
    assert S.c.post("/venues/", json=body, headers=token_only).status_code == 403
    assert S.c.post("/venues/", json=body, headers=hdr(S.admin)).status_code == 201


# ------------------------------------------------------------------ venues & events
def test_venue_create_edit_and_hire_flag(S):
    body = {"name": "Second Hall", "location": "Campus", "capacity": 80, "price_per_hour": 100, "open_for_hire": False}
    v = S.c.post("/venues/", json=body, headers=hdr(S.admin)).json()
    assert v["open_for_hire"] is False
    body["capacity"], body["open_for_hire"] = 90, True
    r = S.c.put(f"/venues/{v['id']}", json=body, headers=hdr(S.admin)).json()
    assert r["capacity"] == 90 and r["open_for_hire"] is True
    assert all(x["open_for_hire"] for x in S.c.get("/venues/?for_hire=true").json())


def event_body(S, **kw):
    start = now_local() + timedelta(days=20)
    b = {"title": "New Event", "category": "Concert", "venue_id": S.venue.id, "start_time": start.isoformat(),
         "end_time": (start + timedelta(hours=2)).isoformat(), "capacity": 50, "status": "draft",
         "categories": [{"name": "General", "price": 100, "total_quantity": 30}]}
    b.update(kw)
    return b


def test_event_draft_publish_and_cancel(S):
    r = S.c.post("/events/", json=event_body(S), headers=hdr(S.admin))
    assert r.status_code == 201 and r.json()["status"] == "draft" and len(r.json()["categories"]) == 1
    eid = r.json()["id"]
    assert all(e["id"] != eid for e in S.c.get("/events/").json())  # drafts are not public
    assert S.c.put(f"/events/{eid}/publish", headers=hdr(S.admin)).status_code == 200
    assert any(e["id"] == eid for e in S.c.get("/events/").json())
    assert S.c.post(f"/events/{eid}/cancel", headers=hdr(S.admin)).json()["status"] == "cancelled"


def test_event_capacity_rules(S):
    assert S.c.post("/events/", json=event_body(S, capacity=500), headers=hdr(S.admin)).status_code == 400   # > venue capacity
    assert S.c.post("/events/", json=event_body(S, capacity=20), headers=hdr(S.admin)).status_code == 422    # tickets 30 > capacity 20
    eid = S.c.post("/events/", json=event_body(S), headers=hdr(S.admin)).json()["id"]
    r = S.c.post(f"/events/{eid}/categories", json={"name": "VIP", "price": 10, "total_quantity": 25}, headers=hdr(S.admin))
    assert r.status_code == 400  # 30 + 25 > 50


def test_event_search_and_filters(S):
    assert len(S.c.get("/events/").json()) == 1
    assert len(S.c.get("/events/?q=Test").json()) == 1 and S.c.get("/events/?q=nothing").json() == []
    assert len(S.c.get("/events/?category=Workshop").json()) == 1 and S.c.get("/events/?category=Concert").json() == []
    assert S.c.get("/events/?max_price=50").json() == []


# ------------------------------------------------------------------ booking & concurrency
def test_overbooking_is_rejected(S):
    assert book(S, qty=2).status_code == 201
    r = book(S)
    assert r.status_code == 409 and "sold out" in r.json()["detail"].lower()
    S.db.refresh(S.cat)
    assert S.cat.available_quantity == 0


def test_last_seat_race_is_atomic(S):
    """Simulates two buyers: another request already took a seat, so only 1 is left.
    The atomic conditional UPDATE (available >= qty) must refuse a 2-ticket sale and allow a 1-ticket sale."""
    S.db.query(TicketCategory).filter_by(id=S.cat.id).update({TicketCategory.available_quantity: 1}, synchronize_session=False)
    S.db.commit()
    assert book(S, qty=2).status_code == 409
    assert book(S, qty=1).status_code == 201
    S.db.refresh(S.cat)
    assert S.cat.available_quantity == 0


def test_booking_issues_unique_qr_and_payment_reference(S):
    r = book(S, qty=2)
    j = r.json()
    assert r.status_code == 201 and len(j["tickets"]) == 2 and j["payment_reference"].startswith("SIM-")
    assert len({t["qr_code"] for t in j["tickets"]}) == 2 and all(len(t["qr_code"]) >= 40 for t in j["tickets"])
    assert S.db.query(Payment).filter_by(payment_reference=j["payment_reference"]).count() == 1
    mine = S.c.get("/bookings/mine", headers=hdr(S.attendee)).json()
    assert mine[0]["tickets"][0]["qr_image"].startswith("data:image/png;base64,")


def test_max_six_tickets_per_booking(S):
    assert S.c.post("/bookings/", json={"event_id": S.event.id, "ticket_category_id": S.cat.id, "quantity": 7}, headers=hdr(S.attendee)).status_code == 422
    r = ask(S, "BookingAgent", {"action": "book", "user_id": S.attendee.id, "event_id": S.event.id, "ticket_category_id": S.cat.id, "quantity": 7})
    assert r["performative"] == "REFUSE" and "6" in r["content"]["reason"]


def test_cancel_refund_policy(S):
    b = book(S).json()["booking_id"]
    r = S.c.post(f"/bookings/{b}/cancel", headers=hdr(S.attendee)).json()
    assert r["refund_amount"] == "100.00"       # event is 5 days away -> full refund
    S.db.refresh(S.cat)
    assert S.cat.available_quantity == 2        # seat returned
    assert S.db.query(Ticket).filter_by(booking_id=b).first().status == "cancelled"
    b2 = book(S).json()["booking_id"]
    S.event.start_time = now_local() + timedelta(hours=10)
    S.event.end_time = S.event.start_time + timedelta(hours=2)
    S.db.commit()
    assert S.c.post(f"/bookings/{b2}/cancel", headers=hdr(S.attendee)).json()["refund_amount"] == "0.00"  # inside 48h


def test_cancelling_event_refunds_everyone_and_voids_tickets(S):
    b = book(S, qty=2).json()
    r = S.c.post(f"/events/{S.event.id}/cancel", headers=hdr(S.admin))
    assert r.status_code == 200 and r.json()["bookings_refunded"] == 1 and r.json()["refunded_total"] == "200.00"
    assert S.db.get(Booking, b["booking_id"]).status == "cancelled"
    assert all(t.status == "cancelled" for t in S.db.query(Ticket).all())
    assert S.db.query(Notification).filter_by(user_id=S.attendee.id).count() >= 2
    assert book(S).status_code == 404


# ------------------------------------------------------------------ check-in
def test_double_checkin_rejected(S):
    b = book(S).json()
    open_window(S)
    payload = {"event_id": S.event.id, "qr_code": b["tickets"][0]["qr_code"]}
    assert S.c.post("/tickets/check-in", json=payload, headers=hdr(S.staff)).json()["admitted"] is True
    second = S.c.post("/tickets/check-in", json=payload, headers=hdr(S.staff)).json()
    assert second["admitted"] is False and second["reason"] == "Already used"
    assert json.loads(S.db.query(AgentState).filter_by(agent_name="TicketAgent").first().state_json)["repeat_scans"] == 1


def test_checkin_rejection_reasons(S):
    t = book(S, qty=2).json()["tickets"]
    other = Event(title="Other", category="Other", venue_id=S.venue.id, organiser_id=S.admin.id, start_time=now_local() + timedelta(days=30),
                  end_time=now_local() + timedelta(days=30, hours=2), capacity=10, status="published")
    S.db.add(other)
    S.db.commit()
    scan = lambda code, eid=S.event.id: S.c.post("/tickets/check-in", json={"event_id": eid, "qr_code": code}, headers=hdr(S.staff)).json()
    assert scan(t[0]["qr_code"])["reason"] == "Outside check-in time"        # event is 5 days away
    assert scan(t[0]["qr_code"], other.id)["reason"] == "Ticket belongs to another event"
    assert scan("nonsense")["reason"] == "Unknown ticket"
    S.db.query(Ticket).filter_by(qr_code=t[1]["qr_code"]).update({Ticket.status: "cancelled"})
    S.db.commit()
    open_window(S)
    assert scan(t[1]["qr_code"])["reason"] == "Ticket is cancelled or invalid"


# ------------------------------------------------------------------ private venue hire
def day(n, h):
    return (now_local() + timedelta(days=n)).replace(hour=h, minute=0, second=0, microsecond=0)


def hire(S, start, end, guests=20, venue=None, user=None):
    return S.c.post("/venue-hire/", json={"venue_id": (venue or S.venue).id, "start_time": start.isoformat(), "end_time": end.isoformat(),
                                          "purpose": "Farewell party", "guest_count": guests}, headers=hdr(user or S.attendee))


def test_routine_hire_is_confirmed_and_priced(S):
    r = hire(S, day(3, 10), day(3, 12)).json()
    assert r["hire"]["status"] == "confirmed" and r["hire"]["quoted_price"] == "2000.00" and r["performative"] == "AGREE"


def test_hire_clash_gets_alternatives(S):
    r = hire(S, S.event.start_time, S.event.start_time + timedelta(hours=1)).json()
    assert r["performative"] == "PROPOSE" and r["hire"]["status"] == "alternatives_offered"
    assert "clash" in r["decision"]["reason"].lower() and len(r["decision"]["alternatives"]) >= 1
    assert all({"venue_id", "start", "end"} <= set(a) for a in r["decision"]["alternatives"])


def test_hire_over_capacity_proposes_other_venues(S):
    from app.models import Venue
    big = Venue(name="Big Hall", location="Campus", capacity=500, price_per_hour=3000)
    S.db.add(big)
    S.db.commit()
    r = hire(S, day(3, 10), day(3, 12), guests=300).json()
    assert r["performative"] == "PROPOSE" and r["decision"]["alternatives"][0]["venue_id"] == big.id


def test_non_routine_hire_is_escalated_and_admin_decides(S):
    r = hire(S, day(3, 9), day(3, 18)).json()                  # 9 hours -> not routine
    assert r["hire"]["status"] == "escalated"
    hid = r["hire"]["id"]
    assert S.c.post(f"/venue-hire/{hid}/decision?decision=confirmed", headers=hdr(S.attendee)).status_code == 403
    assert S.c.get("/venue-hire/escalated", headers=hdr(S.admin)).json()[0]["id"] == hid
    assert S.c.post(f"/venue-hire/{hid}/decision?decision=confirmed", headers=hdr(S.admin)).json()["status"] == "confirmed"
    assert S.db.query(Notification).filter(Notification.user_id == S.admin.id, Notification.title.like("Venue hire needs%")).count() == 1


def test_confirmed_hire_blocks_event_creation(S):
    hire(S, day(8, 10), day(8, 12))
    r = S.c.post("/events/", json=event_body(S, start_time=day(8, 11).isoformat(), end_time=day(8, 13).isoformat()), headers=hdr(S.admin))
    assert r.status_code == 409


# ------------------------------------------------------------------ waitlist
def test_waitlist_offer_hold_and_accept(S):
    other = User(full_name="Other", email="o@test.com", hashed_password=hash_password("password123"), role="attendee")
    S.db.add(other)
    S.db.commit()
    first = book(S, qty=2).json()["booking_id"]
    assert S.c.post("/waitlist/", json={"event_id": S.event.id, "ticket_category_id": S.cat.id, "quantity": 1}, headers=hdr(other)).status_code == 201
    S.c.post(f"/bookings/{first}/cancel", headers=hdr(S.attendee))              # BookingAgent broadcasts seats_released
    entry = S.db.query(WaitlistEntry).filter_by(user_id=other.id).first()
    S.db.refresh(entry); S.db.refresh(S.cat)
    assert entry.status == "offered" and S.cat.available_quantity == 1           # 2 freed, 1 held for the waiting user
    r = S.c.post(f"/waitlist/{entry.id}/accept", headers=hdr(other))
    assert r.status_code == 201 and len(r.json()["tickets"]) == 1
    S.db.refresh(S.cat)
    assert S.cat.available_quantity == 1


def test_waitlist_agent_expiry_sweep_releases_and_reoffers(S):
    other = User(full_name="Other", email="o@test.com", hashed_password=hash_password("password123"), role="attendee")
    S.db.add(other)
    S.db.commit()
    S.db.query(TicketCategory).filter_by(id=S.cat.id).update({TicketCategory.available_quantity: 1}, synchronize_session=False)  # 1 seat is held
    old = WaitlistEntry(user_id=S.attendee.id, event_id=S.event.id, ticket_category_id=S.cat.id, quantity=1, status="offered",
                        offered_at=now_local() - timedelta(minutes=20), expires_at=now_local() - timedelta(minutes=1))
    nxt = WaitlistEntry(user_id=other.id, event_id=S.event.id, ticket_category_id=S.cat.id, quantity=1, status="waiting")
    S.db.add_all([old, nxt])
    S.db.commit()
    assert WaitlistAgent(S.db).tick() == 1                                       # proactive: no user action
    S.db.refresh(old); S.db.refresh(nxt)
    assert old.status == "expired" and nxt.status == "offered"
    assert S.db.query(Notification).filter_by(user_id=other.id, title="Tickets available!").count() == 1


# ------------------------------------------------------------------ agents (message level)
def test_venue_agent_rejects_overlap_and_buffer(S):
    r = ask(S, "VenueAgent", {"action": "check_slot", "venue_id": S.venue.id, "start": S.event.start_time.isoformat(), "end": S.event.end_time.isoformat()})
    assert r["performative"] == "REFUSE" and r["content"]["reason"]
    s = S.event.end_time + timedelta(minutes=10)                                  # inside the 30-minute turnaround buffer
    assert ask(S, "VenueAgent", {"action": "check_slot", "venue_id": S.venue.id, "start": s.isoformat(), "end": (s + timedelta(hours=1)).isoformat()})["performative"] == "REFUSE"
    s = S.event.end_time + timedelta(minutes=45)
    assert ask(S, "VenueAgent", {"action": "check_slot", "venue_id": S.venue.id, "start": s.isoformat(), "end": (s + timedelta(hours=1)).isoformat()})["performative"] == "AGREE"


def test_booking_agent_quantity_and_inventory_rules(S):
    assert BookingAgent(S.db).assess(S.cat, 7)["decision"] == "REFUSE"
    assert BookingAgent(S.db).assess(S.cat, 3)["reason"] == "Insufficient ticket inventory"
    assert BookingAgent(S.db).assess(S.cat, 2)["decision"] == "AGREE"


def test_ticket_agent_rejects_unknown_code(S):
    r = ask(S, "TicketAgent", {"action": "check_in", "qr_code": "not-a-real-code", "event_id": S.event.id})
    assert r["performative"] == "REFUSE" and r["content"]["admitted"] is False


def test_notification_agent_persists_notification_from_inform(S):
    r = ask(S, "NotificationAgent", {"user_id": S.attendee.id, "title": "Test", "message": "Hello"}, perf="INFORM")
    assert r["performative"] == "AGREE"
    assert S.db.query(Notification).filter_by(user_id=S.attendee.id, title="Test").count() == 1
    assert ask(S, "NotificationAgent", {"x": 1}, perf="REQUEST")["performative"] == "REFUSE"


def test_agent_state_persists_between_instances(S):
    book(S)
    assert json.loads(S.db.query(AgentState).filter_by(agent_name="BookingAgent").first().state_json)["bookings_confirmed"] == 1
    assert BookingAgent(S.db).state["bookings_confirmed"] == 1


# ------------------------------------------------------------------ messaging & traceability
def test_message_envelope_and_broadcast(S):
    m = AgentBus(S.db).send("VenueAgent", "NotificationAgent", "INFORM", {"reason": "test"}, "conv-1")
    assert set(m) == {"sender", "receiver", "performative", "content", "conversation_id"}
    S.db.commit()
    assert S.db.query(AgentMessage).filter_by(conversation_id="conv-1").count() == 1
    AgentBus(S.db).broadcast("BookingAgent", {"event": "something_else"}, "conv-2")
    assert S.db.query(AgentMessage).filter_by(conversation_id="conv-2", receiver="ALL").count() == 1


def test_one_booking_is_traceable_across_agents_on_dashboard(S):
    book(S)
    cid = S.db.query(AgentMessage).filter_by(sender="BookingAPI").order_by(AgentMessage.id.desc()).first().conversation_id
    seen = {x for m in S.db.query(AgentMessage).filter_by(conversation_id=cid) for x in (m.sender, m.receiver)}
    assert {"BookingAgent", "TicketAgent", "NotificationAgent"} <= seen
    d = S.c.get("/admin/dashboard", headers=hdr(S.admin)).json()
    assert d["events"][0]["tickets_sold"] == 1 and float(d["events"][0]["revenue"]) == 100
    assert any(m["conversation_id"] == cid for m in d["agent_messages"]) and d["agent_states"]
    assert d["totals"]["tickets_sold"] == 1

def test_outside_window_gives_open_close_detail(S):
    t = book(S).json()["tickets"][0]["qr_code"]
    r = S.c.post("/tickets/check-in", json={"event_id": S.event.id, "qr_code": t}, headers=hdr(S.staff)).json()
    assert r["admitted"] is False and r["reason"] == "Outside check-in time" and "open" in r["detail"]