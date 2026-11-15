"""WaitlistAgent: passes freed seats to waiting customers (reactive + proactive)."""
import uuid
from datetime import timedelta
from app.agents.base import BaseAgent
from app.agents.bus import register
from app.models import Event, TicketCategory, WaitlistEntry
from app.timeutil import now_local


@register
class WaitlistAgent(BaseAgent):
    """Goal: pass freed seats to waiting customers.
    RULES
      W1 Join only when the category cannot satisfy the quantity; one active entry per user per category.
      W2 First come, first served (oldest waiting entry whose quantity fits).
      W3 An offer HOLDS the seats (taken from inventory via BookingAgent) for 10 minutes.
      W4 PROACTIVE: every 30 s tick() expires unclaimed holds, returns the seats and re-offers them.
      W5 REACTIVE: on an INFORM seats_released broadcast it offers seats immediately.
      W6 When an event is cancelled (REQUEST close_event), close every waiting/offered entry and notify each person.
    """
    name = "WaitlistAgent"
    HOLD_MINUTES = 10

    def handle(self, m):
        c = m["content"]
        if m["performative"] == "INFORM":
            if c.get("event") != "seats_released":
                return None
            self.bump("seat_release_events")
            n = self.offer_next(c["event_id"], c["ticket_category_id"], m["conversation_id"])
            return self.reply(m, "AGREE", {"offers_made": n})
        if m["performative"] != "REQUEST":
            return None
        fn = {"join": self._join, "accept": self._accept, "decline": self._decline,
              "close_event": self._close_event}.get(c.get("action"))
        return fn(m) if fn else self.reply(m, "REFUSE", {"reason": "Unknown action"})

    def _join(self, m):
        c = m["content"]
        event = self.db.get(Event, c["event_id"])
        cat = self.db.get(TicketCategory, c["ticket_category_id"])
        if not event or event.status != "published" or not cat or cat.event_id != event.id:
            return self.reply(m, "REFUSE", {"reason": "Ticket category not found", "code": "NOT_FOUND"})
        if now_local() >= event.start_time:
            return self.reply(m, "REFUSE", {"reason": "The event has already started"})
        qty = int(c["quantity"])
        if cat.available_quantity >= qty:
            return self.reply(m, "REFUSE", {"reason": "Tickets are currently available; book directly"})
        if self.db.query(WaitlistEntry).filter(WaitlistEntry.user_id == c["user_id"], WaitlistEntry.ticket_category_id == cat.id,
                                               WaitlistEntry.status.in_(["waiting", "offered"])).first():
            return self.reply(m, "REFUSE", {"reason": "You are already on the waitlist for this category"})
        e = WaitlistEntry(user_id=c["user_id"], event_id=event.id, ticket_category_id=cat.id, quantity=qty, status="waiting")
        self.db.add(e)
        self.db.flush()
        self.bump("joined")
        pos = self.db.query(WaitlistEntry).filter_by(ticket_category_id=cat.id, status="waiting").filter(WaitlistEntry.id <= e.id).count()
        return self.reply(m, "AGREE", {"waitlist_id": e.id, "status": "waiting", "position": pos})

    def _accept(self, m):
        c, cid = m["content"], m["conversation_id"]
        e = self.db.get(WaitlistEntry, c["entry_id"])
        if not e or e.user_id != c["user_id"] or e.status != "offered":
            return self.reply(m, "REFUSE", {"reason": "No active offer found", "code": "NOT_FOUND"})
        if e.expires_at <= now_local():
            return self.reply(m, "REFUSE", {"reason": "This offer has expired"})
        r = self.ask("BookingAgent", {"action": "book", "user_id": e.user_id, "event_id": e.event_id,
                                      "ticket_category_id": e.ticket_category_id, "quantity": e.quantity, "held": True}, cid)
        if r["performative"] != "AGREE":
            return self.reply(m, "REFUSE", {"reason": r["content"].get("reason", "Booking failed")})
        e.status = "accepted"
        self.db.flush()
        self.bump("accepted")
        return self.reply(m, "AGREE", r["content"])

    def _decline(self, m):
        c, cid = m["content"], m["conversation_id"]
        e = self.db.get(WaitlistEntry, c["entry_id"])
        if not e or e.user_id != c["user_id"] or e.status not in ("offered", "waiting"):
            return self.reply(m, "REFUSE", {"reason": "Waitlist entry not found", "code": "NOT_FOUND"})
        was_offered = e.status == "offered"
        e.status = "declined"
        self.db.flush()
        if was_offered:
            self.ask("BookingAgent", {"action": "release", "ticket_category_id": e.ticket_category_id, "quantity": e.quantity}, cid)
            self.offer_next(e.event_id, e.ticket_category_id, cid)
        self.bump("declined")
        return self.reply(m, "AGREE", {"status": "declined"})

    def _close_event(self, m):
        """Event cancelled: close every active waitlist entry and tell each person."""
        c, cid = m["content"], m["conversation_id"]
        event = self.db.get(Event, c["event_id"])
        title = event.title if event else "Event"
        entries = self.db.query(WaitlistEntry).filter(
            WaitlistEntry.event_id == c["event_id"], WaitlistEntry.status.in_(["waiting", "offered"])).all()
        for w in entries:
            w.status = "cancelled"
            self.tell("NotificationAgent", {"user_id": w.user_id, "title": f"{title} cancelled",
                                            "message": "The event was cancelled, so your waitlist entry was closed."}, cid)
        self.db.flush()
        self.bump("entries_closed", len(entries))
        return self.reply(m, "AGREE", {"closed": len(entries)})

    def offer_next(self, event_id, category_id, cid):
        event = self.db.get(Event, event_id)
        if not event or event.status != "published" or event.start_time <= now_local():
            return 0
        offered = 0
        while True:
            e = self.db.query(WaitlistEntry).filter_by(event_id=event_id, ticket_category_id=category_id, status="waiting") \
                .order_by(WaitlistEntry.created_at, WaitlistEntry.id).first()
            cat = self.db.get(TicketCategory, category_id)
            self.db.refresh(cat)
            if not e or cat.available_quantity < e.quantity:
                break
            r = self.ask("BookingAgent", {"action": "hold", "ticket_category_id": category_id, "quantity": e.quantity}, cid)
            if r["performative"] != "AGREE":
                break
            now = now_local()
            e.status, e.offered_at, e.expires_at = "offered", now, now + timedelta(minutes=self.HOLD_MINUTES)
            self.db.flush()
            self.bump("offers")
            self.tell("NotificationAgent", {"user_id": e.user_id, "title": "Tickets available!",
                                            "message": f"{e.quantity} ticket(s) for {event.title} are held for you for {self.HOLD_MINUTES} minutes. Open My tickets > Waitlist to claim them."}, cid)
            offered += 1
        return offered

    def expire_sweep(self):
        """Proactive behaviour: runs on a timer with no user action."""
        cid, now = str(uuid.uuid4()), now_local()
        expired = self.db.query(WaitlistEntry).filter(WaitlistEntry.status == "offered", WaitlistEntry.expires_at <= now).all()
        touched = set()
        for e in expired:
            e.status = "expired"
            self.db.flush()
            self.bus.request(self.name, "BookingAgent", "REQUEST", {"action": "release", "ticket_category_id": e.ticket_category_id, "quantity": e.quantity}, cid)
            self.tell("NotificationAgent", {"user_id": e.user_id, "title": "Ticket offer expired",
                                            "message": "Your ticket hold expired. The tickets were passed to the next person in the queue."}, cid)
            touched.add((e.event_id, e.ticket_category_id))
        if expired:
            self.bump("expired_holds", len(expired))
        for ev, cat in touched:
            self.offer_next(ev, cat, cid)
        # also offer seats that became free by other means to anyone still waiting
        waiting = {(w.event_id, w.ticket_category_id) for w in self.db.query(WaitlistEntry).filter_by(status="waiting")}
        for ev, cat in waiting - touched:
            self.offer_next(ev, cat, cid)
        self.db.commit()
        return len(expired)

    tick = expire_sweep