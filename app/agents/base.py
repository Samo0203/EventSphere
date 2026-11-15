"""Shared base class and helpers for all EventSphere agents."""
import json
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from app.agents.bus import AgentBus
from app.models import AgentState
from app.timeutil import now_local


def money(x) -> Decimal:
    return Decimal(str(x)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def iso(d: datetime) -> str:
    return d.isoformat(timespec="minutes")


class BaseAgent:
    name = "BaseAgent"

    def __init__(self, db):
        self.db, self.bus = db, AgentBus(db)
        row = db.query(AgentState).filter_by(agent_name=self.name).first()
        if not row:
            row = AgentState(agent_name=self.name, state_json="{}")
            db.add(row)
            db.flush()
        self.row = row
        self.state = json.loads(row.state_json or "{}")

    # --- persistent beliefs ---
    def save(self):
        self.row.state_json = json.dumps(self.state)
        self.row.updated_at = now_local()
        self.db.flush()

    def bump(self, key, n=1):
        self.state[key] = self.state.get(key, 0) + n
        self.save()

    # --- messaging helpers (all communication goes through the bus) ---
    def send(self, to, perf, content, cid=None):
        return self.bus.send(self.name, to, perf, content, cid)

    def reply(self, msg, perf, content):
        return self.bus.send(self.name, msg["sender"], perf, content, msg["conversation_id"])

    def ask(self, to, content, cid):
        return self.bus.request(self.name, to, "REQUEST", content, cid)

    def tell(self, to, content, cid):
        return self.bus.request(self.name, to, "INFORM", content, cid)

    def handle(self, message):  # pragma: no cover
        raise NotImplementedError