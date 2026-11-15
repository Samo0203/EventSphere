import json
import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.agents import agents  # noqa: F401
from app.agents.bus import AgentBus
from app.database import get_db
from app.models import Venue, VenueHire
from app.routers.common import respond
from app.schemas import HireIn
from app.security import current_user, roles

router = APIRouter(prefix="/venue-hire", tags=["Private Venue Hire"])


def hire_dict(h, admin=False):
    d = {"id": h.id, "venue_id": h.venue_id, "venue_name": h.venue.name, "start_time": h.start_time.isoformat(),
         "end_time": h.end_time.isoformat(), "purpose": h.purpose, "guest_count": h.guest_count,
         "quoted_price": str(h.quoted_price), "status": h.status, "decision_reason": h.decision_reason,
         "alternatives": json.loads(h.alternatives_json or "[]")}
    if admin:
        d["user_name"], d["user_email"] = h.user.full_name, h.user.email
    return d


@router.post("/", status_code=201)
def request_hire(data: HireIn, db: Session = Depends(get_db), u=Depends(current_user)):
    venue = db.query(Venue).filter_by(id=data.venue_id).first()
    if not venue:
        raise HTTPException(404, "Venue not found")
    h = VenueHire(user_id=u.id, venue_id=venue.id, event_date=data.event_date or data.start_time, start_time=data.start_time,
                  end_time=data.end_time, purpose=data.purpose, guest_count=data.guest_count, quoted_price=0, status="pending")
    db.add(h)
    db.flush()
    reply = AgentBus(db).call("HireAPI", "VenueAgent", "REQUEST", {"action": "hire", "hire_id": h.id}, str(uuid.uuid4()))
    if reply["performative"] == "FAILURE":
        raise HTTPException(500, reply["content"].get("reason", "Hire decision failed"))
    db.refresh(h)
    return {"hire": hire_dict(h), "decision": reply["content"], "performative": reply["performative"]}


@router.get("/mine")
def my_hires(db: Session = Depends(get_db), u=Depends(current_user)):
    return [hire_dict(h) for h in db.query(VenueHire).filter_by(user_id=u.id).order_by(VenueHire.id.desc()).all()]


@router.get("/")
def all_hires(db: Session = Depends(get_db), u=Depends(roles("admin"))):
    return [hire_dict(h, True) for h in db.query(VenueHire).order_by(VenueHire.id.desc()).all()]


@router.get("/escalated")
def escalated(db: Session = Depends(get_db), u=Depends(roles("admin"))):
    return [hire_dict(h, True) for h in db.query(VenueHire).filter_by(status="escalated").order_by(VenueHire.id).all()]


@router.post("/{hid}/decision")
def admin_decision(hid: int, decision: str, note: str = "", db: Session = Depends(get_db), u=Depends(roles("admin"))):
    if decision not in ("confirmed", "rejected"):
        raise HTTPException(400, "Decision must be confirmed or rejected")
    return respond(AgentBus(db).call("HireAPI", "VenueAgent", "REQUEST",
                                     {"action": "admin_decision", "hire_id": hid, "decision": decision, "note": note, "admin_id": u.id}))
