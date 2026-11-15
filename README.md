# EventSphere: agent-based venue booking & digital ticketing

FastAPI + SQLAlchemy (SQLite locally / PostgreSQL in production) + Bootstrap 5 single-page frontend.
Every booking decision is made by five cooperating agents that talk **only through persisted JSON messages**.

## Features
| Area | What is implemented |
|---|---|
| Accounts & roles | Register/login, Argon2-hashed passwords, roles `admin` / `staff` / `attendee`, role checks on every protected route, CSRF token on every state-changing request |
| Venues | Create/edit venues (name, location, capacity, description, image URL, hourly rate), *available* and *open for private hire* flags |
| Events | Draft / publish / cancel, ticket categories on creation, ticket total ≤ event capacity ≤ venue capacity, no venue overlaps (30-min buffer, also against confirmed hires) |
| Browsing | Mobile-first list, keyword search, category filter (+ venue, date range, max price), tickets left per category |
| Booking | Atomic seat allocation, simulated payment reference, history, cancellation with 48-hour refund policy, event cancellation = automatic full refunds |
| Tickets | One unique 256-bit token + QR per ticket, staff scanner with **phone camera (jsQR)** and manual fallback, admit once only, clear rejection reasons (the "outside check-in time" refusal shows when the window opens and closes) |
| Private hire | Instant decision + price; routine = auto-confirmed; clash/over-capacity = **alternative times & venues**; non-routine = escalated to admin who approves/rejects |
| Waitlist | FIFO, 10-minute seat **hold** with visible countdown, claim/decline in the UI, timer-driven expiry and re-offer |
| Dashboard | Tickets sold, revenue, check-ins, capacity, sales bars, check-ins over time, agent state, message log grouped by conversation id |
| Notifications | Stored per user, shown under *My tickets → Notifications* (unread badge) |

**Other features implemented:** waitlist with timed holds + countdown + automatic re-offer, dashboard charts (sales per event, check-ins over time), advanced search (date range, price range, venue).

## Demo accounts (created automatically on first start when the database is empty)
| Role | Email | Password |
|---|---|---|
| Admin | `admin@eventsphere.lk` | `Admin@12345` |
| Gate staff | `staff@eventsphere.lk` | `Staff@12345` |
| Attendee | `attendee@eventsphere.lk` | `Attendee@12345` |

Set `SEED_DEMO=0` to disable seeding.

## Project layout
```
app/
  main.py              app, lifespan, security headers, waitlist timer
  database.py models.py schemas.py security.py timeutil.py seed.py
  agents/
    bus.py             JSON message bus (send / request / broadcast / call)
    base.py            BaseAgent (state + messaging helpers), money(), iso()
    venue_agent.py     VenueAgent
    booking_agent.py   BookingAgent
    ticket_agent.py    TicketAgent
    waitlist_agent.py  WaitlistAgent
    notification_agent.py  NotificationAgent
    agents.py          imports all five so they register with the bus
  routers/             auth venues events bookings tickets hire waitlist notifications dashboard common
  static/              index.html style.css app.js
tests/                 conftest.py test_system.py (31 tests)
.env.example           template for environment variables
```

## Run locally (Windows CMD)
```bat
cd EventSphere
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
uvicorn app.main:app --reload --env-file .env
```
Open http://127.0.0.1:8000 (API docs: `/docs`). Linux/macOS: `source venv/bin/activate` and `cp .env.example .env`.

Without `--env-file .env` the app still runs, using the built-in defaults (SQLite, dev secret key).

## Environment variables
| Variable | Purpose |
|---|---|
| `DATABASE_URL` | SQLite by default. On Render use the PostgreSQL **Internal Database URL** (`postgres://` is auto-converted) |
| `SECRET_KEY` | Long random string used to sign JWTs. **Required in production**; never commit it |
| `APP_TZ_OFFSET_MINUTES` | Local-time offset of the venues (default `330` = Sri Lanka). Render servers run UTC |
| `SEED_DEMO` | `1` (default) creates demo users/venues/events on an empty DB and keeps the *Gate Test (Demo)* event current |
| `WAITLIST_SWEEP_SECONDS` | Interval of the WaitlistAgent timer (default 30) |
| `CHECKIN_WINDOW_HOURS` | Hours before the start and after the end of an event during which tickets can be scanned (default 2) |
| `DISABLE_WORKER` | `1` turns the waitlist timer off (used by the tests only) |

Generate a secret key with:
```bat
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

## Tests
```bat
pytest
pytest --cov=app
```
31 tests. They cover: hashing, roles, CSRF, venue/event rules, search, overbooking, last-seat race, QR uniqueness, 6-ticket limit,
refund policy, event cancellation refunds, double check-in and every rejection reason (including the open/close detail),
hire (auto-confirm / clash alternatives / capacity / escalation / admin decision), waitlist hold-accept-expiry,
and every agent's rules (through messages), state persistence and traceability.

## Deploy on Render
1. Push to GitHub (`.env` and `*.db` are git-ignored).
2. Render → **New PostgreSQL** (free) → copy the *Internal Database URL*.
3. Render → **New Web Service** from the repo. Runtime Python 3.11+.
   * Build: `pip install -r requirements.txt`
   * Start: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
   * Env: `DATABASE_URL`, `SECRET_KEY` (long random), `APP_TZ_OFFSET_MINUTES=330`
4. Open `/health`, `/docs`, sign in with a demo account, and run a full flow: book *Gate Test (Demo)* as the attendee, then scan it as staff (✅ ADMIT; a second scan says *Already used*).

## Agent design
**Message envelope:** `{sender, receiver, performative, content, conversation_id}`; performatives `REQUEST AGREE REFUSE PROPOSE INFORM FAILURE`.
API routes never decide anything: they send a `REQUEST` through `AgentBus`, and the receiving agent's `handle()` decides and replies.
Agents contact each other the same way (e.g. BookingAgent → TicketAgent `REQUEST issue`; BookingAgent → WaitlistAgent `REQUEST close_event`).
Agents never call each other's methods or edit each other's tables. Every hop is stored in `agent_messages`
and shown on the dashboard grouped by `conversation_id`. Each agent keeps counters/beliefs in `agent_states` (they survive restarts).

**Reactive:** `BookingAgent` broadcasts `INFORM seats_released`, so `WaitlistAgent` offers seats immediately; `NotificationAgent` listens to every INFORM naming a `user_id`.
**Proactive:** `WaitlistAgent.tick()` runs every 30 s with no user action: it expires unclaimed holds, returns the seats and re-offers them to the next person.

| Agent | Goal | Decision rules |
|---|---|---|
| VenueAgent | Calendars free of clashes | V1 refuse missing venue / bad times / past start · V2 refuse overlap with events or confirmed hires incl. 30-min buffer · V3 hire: closed venue → propose other venues; guests > capacity → propose bigger venues · V4 clash → PROPOSE alternative slots + free venues · V5 routine hire (≤ 6 h, 08:00–22:00, ≥ 24 h notice) → AGREE · V6 other feasible hire → ESCALATE to admin · V7 price = hours × hourly rate |
| BookingAgent | Sell fairly, never oversell | B1 max 6 tickets per booking · B2 event must be published and not started · B3 seats taken by one atomic `UPDATE … WHERE available >= qty` · B4 refund 100 % if cancelled ≥ 48 h before start, else 0 %; 100 % if event cancelled · B5 event cancel refunds all, voids tickets, asks the WaitlistAgent to close its queue · B6 broadcast freed seats |
| TicketAgent | Admit each ticket once | T1 unique `token_urlsafe(32)` per ticket · T2 answers: unknown / wrong event / cancelled / already used / outside window / admit · T3 window = `CHECKIN_WINDOW_HOURS` (default 2 h) before start to the same after end; the refusal states when it opens and closes · T4 admit via atomic conditional update · T5 repeat scans counted |
| WaitlistAgent | Pass freed seats on | W1 join only when sold out, one active entry per category · W2 first-come-first-served · W3 offer **holds** seats 10 min · W4 timer expiry + re-offer · W5 reacts to `seats_released` · W6 on event cancellation (`close_event`) close all waiting/offered entries and notify each person |
| NotificationAgent | Tell the right person | N1 store a notification for every INFORM that names a user · N2 ignore events about nobody · N3 refuse non-INFORM with a reason |

**Concurrency:** seat counts change only through a single conditional SQL `UPDATE` (`available_quantity >= qty`). Two simultaneous buyers of the last seat
serialise on the row lock in PostgreSQL; the loser's update matches 0 rows and gets `409 sold out`. Check-in uses the same pattern on `tickets.checked_in`.
Booking, payment, tickets, notification and message log commit in one transaction (all-or-nothing).

**Security:** Argon2 password hashes; JWT (8 h) containing a per-login CSRF secret that must be echoed in the `X-CSRF-Token` header on all POST/PUT/DELETE
(the API uses bearer tokens, not cookies, so forged cross-site forms cannot authenticate in the first place); role checks via `roles(...)` dependencies;
output escaping in the frontend; security headers; secrets only from environment variables.

## Limitations
* Payments are simulated (`SIM-…` references); no email sending (in-app notifications only).
* No schema migrations (Alembic): recreate the DB when models change.
* Agents run in one process and communicate through the persisted message bus rather than over HTTP between separate services.
* Venue images are set by URL (no file upload).