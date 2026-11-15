import asyncio
import logging
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from app.database import Base, SessionLocal, engine
from app.agents.agents import WaitlistAgent
from app.agents.bus import REGISTRY
from app.routers import auth, bookings, dashboard, events, hire, notifications, tickets, venues, waitlist
from app.seed import ensure_live_event, seed_demo

log = logging.getLogger("eventsphere")
STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
SWEEP_SECONDS = int(os.getenv("WAITLIST_SWEEP_SECONDS", "30"))


def _sweep():
    db = SessionLocal()
    try:
        WaitlistAgent(db).tick()
    except Exception:  # noqa: BLE001
        db.rollback()
        log.exception("Waitlist sweep failed")
    finally:
        db.close()


async def waitlist_worker():
    """Proactive behaviour: the WaitlistAgent wakes itself up on a timer, with no user action."""
    while True:
        await asyncio.sleep(SWEEP_SECONDS)
        await asyncio.to_thread(_sweep)


def _bootstrap():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        for cls in REGISTRY.values():  # make sure every agent has a persistent state row
            cls(db)
        db.commit()
        if os.getenv("SEED_DEMO", "1") == "1":
            seed_demo(db)
            ensure_live_event(db)
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    _bootstrap()
    task = None
    if os.getenv("DISABLE_WORKER", "0") != "1":
        task = asyncio.create_task(waitlist_worker())
    yield
    if task:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


app = FastAPI(title="EventSphere", description="Agent-based venue booking and digital ticketing",
              version="3.0.0", lifespan=lifespan)
for r in (auth, venues, events, bookings, tickets, hire, waitlist, notifications, dashboard):
    app.include_router(r.router)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.middleware("http")
async def security_headers(request: Request, call_next):
    resp = await call_next(request)
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("X-Frame-Options", "DENY")
    resp.headers.setdefault("Referrer-Policy", "same-origin")
    resp.headers.setdefault("Permissions-Policy", "camera=(self)")
    return resp


@app.get("/", include_in_schema=False)
def home():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))


@app.get("/health")
def health():
    return {"status": "healthy"}
