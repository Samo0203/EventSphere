# EventSphere — ICA 02 implementation pack

This is a replacement implementation pack based on the supplied project and the IT4123 ICA 02 brief. It includes FastAPI, SQLAlchemy, SQLite locally/PostgreSQL in production, a responsive Bootstrap frontend, role-protected endpoints, simulated payments, unique QR tickets, one-time check-in, private venue hire, five agent classes, persisted JSON message logs, a periodic waitlist expiry worker and Pytest tests.

## Important before using
1. Make a backup of your current `EventSphere` folder and `eventsphere.db`.
2. This version changes database columns and roles. `create_all()` does not migrate existing tables. For a fresh local test, rename the old `eventsphere.db` to `eventsphere_backup.db` before first run. Do not delete your only copy.
3. The public registration endpoint always creates `attendee` accounts. Create the first admin locally with the bootstrap command below. Never allow public self-registration as admin.
4. This is a student implementation baseline. Run the full test suite and manually verify every viva scenario before submission. Camera QR scanning is not yet integrated in this baseline; manual code entry is available. The brief explicitly requires camera scanning, so add/test a browser scanner library before claiming that requirement is complete.
5. The timed waitlist worker expires holds every 30 seconds. This baseline re-offers expired entries by making their status expired and attempting the next queued offer. User-facing acceptance/checkout of a hold still needs to be completed before claiming the advanced timed-hold feature is fully working.

## Local setup (Windows CMD)
```bat
cd EventSphere
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
uvicorn app.main:app --reload
```
Open `http://127.0.0.1:8000` and API docs at `http://127.0.0.1:8000/docs`.

## Create first admin
Register a normal user in the UI, then run:
```bat
python -c "from app.database import SessionLocal; from app.models import User; db=SessionLocal(); u=db.query(User).filter_by(email='YOUR_EMAIL').first(); u.role='admin'; db.commit(); print(u.email, u.role); db.close()"
```
Create staff account by registering normally then set `u.role='staff'` in the same local command. Do not commit credentials.

## Environment variables
- `DATABASE_URL`: local default SQLite; set Render PostgreSQL internal URL in production.
- `SECRET_KEY`: long random secret; set in Render environment variables.

## Tests
```bat
pytest -q
```
The included tests cover registration, role protection, venue creation, published-event browsing, overselling prevention, QR issuance, double check-in, and each of the five agent decision/behaviour paths.

## Render deployment
- Create a PostgreSQL database in Render.
- Set `DATABASE_URL` to the database's internal connection URL.
- Set `SECRET_KEY` to a strong random value.
- Build command: `pip install -r requirements.txt`
- Start command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
- Deploy the web service and verify `/health`, `/docs`, registration/login and a complete booking/check-in flow.
- Use HTTPS public URL in the submission PDF.

## Implemented decision rules
- VenueAgent: refuses unavailable venues and overlaps; applies 30-minute turnaround buffer; checks guest count and offers alternative venues when possible; prices hire by hours × venue hourly rate.
- BookingAgent: maximum six tickets per booking; refuses insufficient inventory; full refund if event cancelled; otherwise full refund at least 48 hours before start and zero inside 48 hours.
- TicketAgent: issues a unique 256-bit-ish URL-safe random token per ticket; rejects unknown, wrong-event, cancelled, already-used and outside-window scans; check-in uses a row lock.
- WaitlistAgent: oldest waiting entry first; offer hold is 10 minutes; background sweep expires offers every 30 seconds and attempts re-offer.
- NotificationAgent: persists user notifications and handles INFORM messages from other agents.

## Agent communication and limitations
Messages are JSON envelopes with sender, receiver, performative, content and conversation_id and are persisted in `agent_messages`. Supported performatives are REQUEST, AGREE, REFUSE, PROPOSE, INFORM and FAILURE. Agent state counters are persisted in `agent_states`. The current app demonstrates the agent decision classes and persisted message bus; expand routing so every business decision is invoked through message dispatch rather than direct agent construction before viva if your lecturer interprets “communicate only through messages” strictly. This baseline should not be represented as a fully distributed HTTPX agent deployment.
