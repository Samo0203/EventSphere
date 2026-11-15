from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.agents import agents  # noqa: F401
from app.agents.bus import AgentBus
from app.database import get_db
from app.models import WaitlistEntry
from app.routers.common import respond
from app.schemas import WaitlistIn
from app.security import current_user

router = APIRouter(prefix="/waitlist", tags=["Waitlist"])


@router.post("/", status_code=201)
def join(data: WaitlistIn, db: Session = Depends(get_db), u=Depends(current_user)):
    return respond(AgentBus(db).call("WaitlistAPI", "WaitlistAgent", "REQUEST", {
        "action": "join", "user_id": u.id, "event_id": data.event_id,
        "ticket_category_id": data.ticket_category_id, "quantity": data.quantity}))


@router.get("/mine")
def mine(db: Session = Depends(get_db), u=Depends(current_user)):
    rows = db.query(WaitlistEntry).filter_by(user_id=u.id).order_by(WaitlistEntry.created_at.desc(), WaitlistEntry.id.desc()).all()
    return [{"id": w.id, "event_id": w.event_id, "event": w.event.title, "category": w.ticket_category.name,
             "quantity": w.quantity, "status": w.status,
             "expires_at": w.expires_at.isoformat() if w.expires_at else None} for w in rows]


@router.post("/{wid}/accept", status_code=201)
def accept(wid: int, db: Session = Depends(get_db), u=Depends(current_user)):
    return respond(AgentBus(db).call("WaitlistAPI", "WaitlistAgent", "REQUEST", {"action": "accept", "entry_id": wid, "user_id": u.id}))


@router.post("/{wid}/decline")
def decline(wid: int, db: Session = Depends(get_db), u=Depends(current_user)):
    return respond(AgentBus(db).call("WaitlistAPI", "WaitlistAgent", "REQUEST", {"action": "decline", "entry_id": wid, "user_id": u.id}))
