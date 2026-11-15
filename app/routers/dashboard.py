import json
from collections import Counter
from typing import Optional
from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import AgentMessage, AgentState, Booking, Event, Payment, Ticket, TicketCategory, VenueHire
from app.security import roles

router = APIRouter(prefix="/admin", tags=["Admin Dashboard"])


@router.get("/dashboard")
def dashboard(conversation_id: Optional[str] = None, db: Session = Depends(get_db), u=Depends(roles("admin"))):
    result = []
    for e in db.query(Event).order_by(Event.start_time).all():
        sold = db.query(func.coalesce(func.sum(Booking.quantity), 0)).filter_by(event_id=e.id, status="confirmed").scalar()
        revenue = db.query(func.coalesce(func.sum(Payment.amount), 0)).join(Booking, Payment.booking_id == Booking.id) \
            .filter(Booking.event_id == e.id, Payment.status == "success").scalar()
        checked = db.query(Ticket).join(Booking).filter(Booking.event_id == e.id, Ticket.checked_in == True).count()  # noqa: E712
        result.append({"event_id": e.id, "title": e.title, "status": e.status, "tickets_sold": int(sold),
                       "revenue": str(revenue), "check_ins": checked, "capacity": e.capacity})
    hours = Counter(t.checked_in_at.strftime("%Y-%m-%d %H:00") for t in
                    db.query(Ticket).filter(Ticket.checked_in == True, Ticket.checked_in_at.isnot(None)).all())  # noqa: E712
    q = db.query(AgentMessage)
    if conversation_id:
        q = q.filter(AgentMessage.conversation_id == conversation_id)
    logs = q.order_by(AgentMessage.id.desc()).limit(300).all()
    return {
        "totals": {"tickets_sold": sum(r["tickets_sold"] for r in result),
                   "revenue": str(sum(float(r["revenue"]) for r in result)),
                   "check_ins": sum(r["check_ins"] for r in result),
                   "pending_hires": db.query(VenueHire).filter_by(status="escalated").count()},
        "events": result,
        "checkins_by_hour": [{"hour": k, "count": v} for k, v in sorted(hours.items())],
        "agent_states": [{"agent": s.agent_name, "state": json.loads(s.state_json or "{}")} for s in db.query(AgentState).order_by(AgentState.agent_name)],
        "agent_messages": [{"id": m.id, "sender": m.sender, "receiver": m.receiver, "performative": m.performative,
                            "content": json.loads(m.content), "conversation_id": m.conversation_id,
                            "created_at": m.created_at.isoformat()} for m in logs],
    }
