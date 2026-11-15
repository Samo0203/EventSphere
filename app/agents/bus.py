"""JSON message bus.

Agents never call each other's methods. They exchange envelopes
{sender, receiver, performative, content, conversation_id}; every hop is persisted in
`agent_messages` so one user action can be traced across agents on the admin dashboard.
"""
import json
import logging
import uuid
from app.models import AgentMessage
from app.timeutil import now_local

log = logging.getLogger("eventsphere.bus")
PERFORMATIVES = {"REQUEST", "AGREE", "REFUSE", "PROPOSE", "INFORM", "FAILURE"}
REGISTRY: dict = {}  # agent name -> agent class (filled by @register in agents.py)


def register(cls):
    REGISTRY[cls.name] = cls
    return cls


class AgentBus:
    def __init__(self, db):
        self.db = db

    def send(self, sender, receiver, performative, content, conversation_id=None):
        """Log one message and return its envelope. (Flushes only; the caller commits.)"""
        if performative not in PERFORMATIVES:
            raise ValueError("Unsupported performative")
        cid = conversation_id or str(uuid.uuid4())
        payload = content if isinstance(content, dict) else {"message": str(content)}
        self.db.add(AgentMessage(sender=sender, receiver=receiver, performative=performative,
                                 content=json.dumps(payload, default=str), conversation_id=cid,
                                 created_at=now_local()))
        self.db.flush()
        return {"sender": sender, "receiver": receiver, "performative": performative,
                "content": payload, "conversation_id": cid}

    def request(self, sender, receiver, performative, content, conversation_id=None):
        """Deliver a message to one agent and return that agent's reply envelope.
        An unexpected error rolls the unit of work back and is reported as a FAILURE reply."""
        env = self.send(sender, receiver, performative, content, conversation_id)
        cid = env["conversation_id"]
        cls = REGISTRY.get(receiver)
        if cls is None:
            return self.send(receiver, sender, "FAILURE", {"reason": f"Unknown agent '{receiver}'"}, cid)
        try:
            reply = cls(self.db).handle(env)
        except Exception as ex:  # noqa: BLE001
            log.exception("Agent %s failed", receiver)
            self.db.rollback()
            return self.send(receiver, sender, "FAILURE", {"reason": str(ex) or type(ex).__name__}, cid)
        return reply or self.send(receiver, sender, "INFORM", {"received": True}, cid)

    def broadcast(self, sender, content, conversation_id=None):
        """INFORM every other agent. Each agent decides on its own whether the event concerns it."""
        env = self.send(sender, "ALL", "INFORM", content, conversation_id)
        cid = env["conversation_id"]
        replies = []
        for name, cls in list(REGISTRY.items()):
            if name == sender:
                continue
            try:
                reply = cls(self.db).handle(env)
            except Exception as ex:  # noqa: BLE001
                log.exception("Agent %s failed on broadcast", name)
                reply = self.send(name, sender, "FAILURE", {"reason": str(ex) or type(ex).__name__}, cid)
            if reply:
                replies.append(reply)
        return replies

    def call(self, sender, receiver, performative, content, conversation_id=None):
        """Top-level entry used by API routes: request + commit the whole unit of work."""
        reply = self.request(sender, receiver, performative, content, conversation_id)
        self.db.commit()
        return reply
