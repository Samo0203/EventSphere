from typing import Optional
from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from app.agents import agents  # noqa: F401  (registers all agents)
from app.agents.bus import PERFORMATIVES, REGISTRY, AgentBus
from app.database import get_db
from app.security import roles

router = APIRouter(prefix="/agents", tags=["Agent inboxes (HTTP)"])


class EnvelopeIn(BaseModel):
    sender: str = Field(default="HttpClient", min_length=1, max_length=60)
    performative: str = Field(default="REQUEST", description="REQUEST, AGREE, REFUSE, PROPOSE, INFORM or FAILURE")
    content: dict = Field(description='JSON content, e.g. {"action": "check_slot", "venue_id": 1, "start": "...", "end": "..."}')
    conversation_id: Optional[str] = Field(default=None, max_length=80)


@router.get("/")
def list_agents(u=Depends(roles("admin", "staff"))):
    """The five agents and their inbox URLs."""
    return [{"agent": n, "goal": (c.__doc__ or "").strip().splitlines()[0], "inbox": f"/agents/{n}/inbox"}
            for n, c in sorted(REGISTRY.items())]


@router.post("/{name}/inbox")
def inbox(name: str, msg: EnvelopeIn, db: Session = Depends(get_db), u=Depends(roles("admin")),
          x_csrf_token: Optional[str] = Header(None, alias="X-CSRF-Token", description="csrf_token returned by /auth/login")):
    """Deliver a JSON message to one agent and return that agent's reply envelope."""
    if name not in REGISTRY:
        raise HTTPException(404, f"Unknown agent '{name}'")
    if msg.performative not in PERFORMATIVES:
        raise HTTPException(400, "Performative must be one of " + ", ".join(sorted(PERFORMATIVES)))
    return AgentBus(db).call(msg.sender, name, msg.performative, msg.content, msg.conversation_id)