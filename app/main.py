
from fastapi import FastAPI
from app.routers import auth

app = FastAPI(
    title="EventSphere",
    description="Venue Booking and Digital Ticketing Platform",
    version="1.0.0"
)

app.include_router(auth.router)


@app.get("/")
def home():
    return {
        "message": "Welcome to EventSphere!",
        "status": "Application is running"
    }


@app.get("/health")
def health_check():
    return {"status": "healthy"}
