"""TicketAgent: issues unique tickets and admits each one exactly once."""
import os
import secrets
from datetime import timedelta
from app.agents.base import BaseAgent
from app.agents.bus import register
from app.models import Ticket
from app.timeutil import now_local


@register
class TicketAgent(BaseAgent):
    """Goal: admit each ticket exactly once.
    RULES
      T1 Every ticket gets a unique unguessable token (secrets.token_urlsafe(32), 256 bits).
      T2 Check-in answers: Unknown ticket / wrong event / cancelled / already used / outside window / admit.
      T3 Check-in window is 2 hours before start to 2 hours after end (CHECKIN_WINDOW_HOURS). The refusal says when it opens/closes.
      T4 Admission is one atomic conditional UPDATE (checked_in = false), so simultaneous scans admit once.
      T5 Repeated scans of a used ticket are remembered (state: repeat_scans).
    """
    name = "TicketAgent"
    WINDOW = timedelta(hours=float(os.getenv("CHECKIN_WINDOW_HOURS", "2")))

    def handle(self, m):
        if m["performative"] != "REQUEST":
            return None
        a = m["content"].get("action")
        if a == "issue":
            made = [Ticket(booking_id=m["content"]["booking_id"], qr_code=secrets.token_urlsafe(32), status="valid")
                    for _ in range(int(m["content"]["quantity"]))]
            self.db.add_all(made)
            self.db.flush()
            self.bump("issued", len(made))
            return self.reply(m, "AGREE", {"tickets": [{"id": t.id, "qr_code": t.qr_code} for t in made]})
        if a == "void":
            self.db.query(Ticket).filter(Ticket.booking_id == m["content"]["booking_id"]).update({Ticket.status: "cancelled"}, synchronize_session=False)
            self.db.flush()
            self.bump("voided")
            return self.reply(m, "AGREE", {"voided": True})
        if a == "check_in":
            return self._check_in(m)
        return self.reply(m, "REFUSE", {"reason": f"Unknown action '{a}'"})

    def _no(self, m, reason, **extra):
        self.bump("rejected_scans")
        return self.reply(m, "REFUSE", {"admitted": False, "reason": reason, **extra})

    def _check_in(self, m):
        token, event_id = str(m["content"]["qr_code"]).strip(), int(m["content"]["event_id"])
        t = self.db.query(Ticket).filter_by(qr_code=token).first()
        if not t:
            return self._no(m, "Unknown ticket")
        b = t.booking
        if b.event_id != event_id:
            return self._no(m, "Ticket belongs to another event")
        if b.status != "confirmed" or t.status != "valid":
            return self._no(m, "Ticket is cancelled or invalid")
        if t.checked_in:
            self.bump("repeat_scans")
            return self._no(m, "Already used")
        ev, now = b.event, now_local()
        opens, closes = ev.start_time - self.WINDOW, ev.end_time + self.WINDOW
        if now < opens or now > closes:
            fmt = "%d %b %Y %H:%M"
            detail = (f"Check-in for \"{ev.title}\" is open {opens.strftime(fmt)} to {closes.strftime(fmt)} "
                      f"(venue time). It is now {now.strftime(fmt)}.")
            return self._no(m, "Outside check-in time", detail=detail)
        n = self.db.query(Ticket).filter(Ticket.id == t.id, Ticket.checked_in == False) \
            .update({Ticket.checked_in: True, Ticket.checked_in_at: now}, synchronize_session=False)  # noqa: E712
        if n != 1:
            self.bump("repeat_scans")
            return self._no(m, "Already used")
        self.db.flush()
        self.bump("successful_checkins")
        return self.reply(m, "AGREE", {"admitted": True, "reason": "Admit", "ticket_id": t.id, "holder": b.user.full_name})