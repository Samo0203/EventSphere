
from fastapi import FastAPI
from app.routers import auth
from app.routers import auth, venues

app = FastAPI(
    title="EventSphere",
    description="Venue Booking and Digital Ticketing Platform",
    version="1.0.0"
)

app.include_router(auth.router)
app.include_router(venues.router)


@app.get("/")
def home():
    return {
        "message": "Welcome to EventSphere!",
        "status": "Application is running"
    }


@app.get("/health")
def health_check():
    return {"status": "healthy"}
