import json, uuid
from datetime import datetime
from app.models import AgentMessage

PERFORMATIVES = {"REQUEST", "AGREE", "REFUSE", "PROPOSE", "INFORM", "FAILURE"}

class AgentBus:
    """JSON message bus. Agents communicate by envelopes; every hop is persisted."""
    def __init__(self, db):
        self.db = db

    def send(self, sender, receiver, performative, content, conversation_id=None):
        if performative not in PERFORMATIVES:
            raise ValueError("Unsupported performative")
        cid = conversation_id or str(uuid.uuid4())
        payload = content if isinstance(content, dict) else {"message": str(content)}
        self.db.add(AgentMessage(sender=sender, receiver=receiver,
            performative=performative, content=json.dumps(payload),
            conversation_id=cid, created_at=datetime.utcnow()))
        self.db.commit()
        return {"sender": sender, "receiver": receiver, "performative": performative,
                "content": payload, "conversation_id": cid}
