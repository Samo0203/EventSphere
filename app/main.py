import asyncio, os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from app.database import Base, engine, SessionLocal
from app.routers import auth,venues,events,bookings,tickets,hire,waitlist,dashboard
from app.agents.agents import WaitlistAgent

async def waitlist_worker():
    while True:
        db=SessionLocal()
        try: WaitlistAgent(db).expire_sweep()
        except Exception: db.rollback()
        finally: db.close()
        await asyncio.sleep(30)

@asynccontextmanager
async def lifespan(app:FastAPI):
    Base.metadata.create_all(bind=engine)
    task=asyncio.create_task(waitlist_worker())
    yield
    task.cancel()
    try: await task
    except asyncio.CancelledError: pass

app=FastAPI(title="EventSphere",description="Agent-based venue booking and digital ticketing",version="2.0.0",lifespan=lifespan)
app.include_router(auth.router); app.include_router(venues.router); app.include_router(events.router)
app.include_router(bookings.router); app.include_router(tickets.router); app.include_router(hire.router)
app.include_router(waitlist.router); app.include_router(dashboard.router)
app.mount("/static",StaticFiles(directory="app/static"),name="static")

@app.get("/")
def home(): return FileResponse("app/static/index.html")
@app.get("/health")
def health(): return {"status":"healthy"}
