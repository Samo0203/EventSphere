"""Demo data so the viva starts with working accounts. Disabled with SEED_DEMO=0."""
from datetime import timedelta
from app.models import Event, TicketCategory, User, Venue
from app.security import hash_password
from app.timeutil import now_local

DEMO_USERS = [
    ("Demo Admin", "admin@eventsphere.lk", "Admin@12345", "admin"),
    ("Demo Gate Staff", "staff@eventsphere.lk", "Staff@12345", "staff"),
    ("Demo Attendee", "attendee@eventsphere.lk", "Attendee@12345", "attendee"),
]
LIVE_TITLE = "Gate Test (Demo)"


def seed_demo(db):
    if db.query(User).count():
        return
    users = {}
    for name, email, pw, role in DEMO_USERS:
        u = User(full_name=name, email=email, hashed_password=hash_password(pw), role=role)
        db.add(u)
        users[role] = u
    venues = [
        Venue(name="Main Auditorium", location="Faculty of Applied Science, Vavuniya", capacity=300, price_per_hour=5000,
              description="Tiered hall with stage, sound system and projector."),
        Venue(name="Innovation Lab", location="Department of Physical Science", capacity=60, price_per_hour=1500,
              description="Flexible workshop space with movable tables and fast Wi-Fi."),
        Venue(name="Garden Pavilion", location="University Gardens", capacity=120, price_per_hour=2500,
              description="Open-air pavilion perfect for receptions and club meetings."),
    ]
    db.add_all(venues)
    db.flush()
    base = now_local().replace(hour=17, minute=0, second=0, microsecond=0)
    events = [
        ("Campus Beats Live", "Concert", venues[0], base + timedelta(days=7), 3, 250, [("General", 1500, 150), ("VIP", 3500, 50)],
         "An evening of live student bands and guest artists."),
        ("AI in Practice Workshop", "Workshop", venues[1], base + timedelta(days=10, hours=-7), 4, 40, [("Standard", 500, 30), ("Student", 250, 10)],
         "Hands-on introduction to building small AI-powered tools."),
        ("Research Day Seminar", "Seminar", venues[2], base + timedelta(days=14, hours=-8), 3, 100, [("Open entry", 0, 100)],
         "Final-year students present their research projects."),
    ]
    for title, cat, v, start, hrs, cap, tickets, desc in events:
        e = Event(title=title, category=cat, description=desc, venue_id=v.id, organiser_id=users["admin"].id,
                  start_time=start, end_time=start + timedelta(hours=hrs), capacity=cap, status="published")
        db.add(e)
        db.flush()
        for n, p, q in tickets:
            db.add(TicketCategory(event_id=e.id, name=n, price=p, total_quantity=q, available_quantity=q))
    db.commit()


def ensure_live_event(db):
    """Keeps one demo event that starts in ~1 hour: it is still bookable, and its check-in window
    (opens 2 h before start) is already open, so book -> scan can be shown at any time during the viva."""
    admin = db.query(User).filter_by(role="admin").order_by(User.id).first()
    venue = db.query(Venue).filter_by(name="Garden Pavilion").first() or db.query(Venue).order_by(Venue.id).first()
    if not admin or not venue:
        return
    now = now_local()
    start = now.replace(second=0, microsecond=0) + timedelta(hours=1)
    ev = db.query(Event).filter_by(title=LIVE_TITLE).first()
    if ev is None:
        ev = Event(title=LIVE_TITLE, category="Other", description="Demo event for testing booking and the QR scanner.",
                   venue_id=venue.id, organiser_id=admin.id, start_time=start, end_time=start + timedelta(hours=3),
                   capacity=30, status="published")
        db.add(ev)
        db.flush()
        db.add(TicketCategory(event_id=ev.id, name="Free entry", price=0, total_quantity=30, available_quantity=30))
    elif ev.status == "published" and ev.start_time < now + timedelta(minutes=15):
        ev.start_time, ev.end_time = start, start + timedelta(hours=3)   # slide the window forward
    db.commit()