
from fastapi import FastAPI
from app.routers import auth, venues, events, ticket_categories, bookings
app = FastAPI(
    title="EventSphere",
    description="Venue Booking and Digital Ticketing Platform",
    version="1.0.0"
)

app.include_router(auth.router)
app.include_router(venues.router)
app.include_router(events.router)
app.include_router(ticket_categories.router)
app.include_router(bookings.router)


@app.get("/")
def home():
    return {
        "message": "Welcome to EventSphere!",
        "status": "Application is running"
    }


@app.get("/health")
def health_check():
    return {"status": "healthy"}
