"""BookingAgent: sells tickets without overselling, calculates refunds."""
import secrets
from decimal import Decimal
from sqlalchemy import case
from app.agents.base import BaseAgent, money
from app.agents.bus import register
from app.models import Booking, Event, Payment, TicketCategory, WaitlistEntry
from app.timeutil import now_local


@register
class BookingAgent(BaseAgent):
    """Goal: sell tickets fairly without overselling.
    RULES
      B1 Refuse more than 6 tickets per booking (or fewer than 1).
      B2 Refuse bookings for unpublished/cancelled events, or after the event has started.
      B3 Refuse if the category has too few tickets. Seats are taken with one atomic conditional UPDATE
         (available >= qty), so two simultaneous buyers can never take the same last seat.
      B4 Refund: 100% if the event is cancelled; 100% if cancelled >= 48 h before start; otherwise 0%.
      B5 Cancelling an event refunds every confirmed booking in full, voids tickets, closes the waitlist.
      B6 Freed seats are broadcast (INFORM seats_released) so the WaitlistAgent can react.
    """
    name = "BookingAgent"
    MAX_PER_BOOKING = 6
    REFUND_HOURS = 48

    def assess(self, category, quantity):
        if quantity < 1 or quantity > self.MAX_PER_BOOKING:
            return {"decision": "REFUSE", "reason": "Maximum 6 tickets per booking"}
        if not category or category.available_quantity < quantity:
            return {"decision": "REFUSE", "reason": "Insufficient ticket inventory"}
        return {"decision": "AGREE", "reason": "Inventory and quantity rules passed"}

    def refund_amount(self, booking, event):
        if event.status == "cancelled":
            return money(booking.total_amount)
        hours = (event.start_time - now_local()).total_seconds() / 3600
        return money(booking.total_amount) if hours >= self.REFUND_HOURS else Decimal("0.00")

    def _take(self, category_id, qty):
        n = self.db.query(TicketCategory).filter(TicketCategory.id == category_id, TicketCategory.available_quantity >= qty) \
            .update({TicketCategory.available_quantity: TicketCategory.available_quantity - qty}, synchronize_session=False)
        return n == 1

    def _release(self, category_id, qty):
        t = TicketCategory
        self.db.query(t).filter(t.id == category_id).update({t.available_quantity: case(
            (t.available_quantity + qty > t.total_quantity, t.total_quantity), else_=t.available_quantity + qty)},
            synchronize_session=False)

    def handle(self, m):
        if m["performative"] != "REQUEST":
            return None
        a = m["content"].get("action")
        fn = {"book": self._book, "cancel": self._cancel, "cancel_event": self._cancel_event,
              "hold": self._hold, "release": self._release_req}.get(a)
        return fn(m) if fn else self.reply(m, "REFUSE", {"reason": f"Unknown action '{a}'"})

    def _hold(self, m):
        c = m["content"]
        if self._take(c["ticket_category_id"], int(c["quantity"])):
            self.bump("holds_granted")
            return self.reply(m, "AGREE", {"held": int(c["quantity"])})
        return self.reply(m, "REFUSE", {"reason": "Not enough seats to hold", "code": "SOLD_OUT"})

    def _release_req(self, m):
        c = m["content"]
        self._release(c["ticket_category_id"], int(c["quantity"]))
        self.db.flush()
        self.bump("holds_released")
        return self.reply(m, "AGREE", {"released": int(c["quantity"])})

    def _book(self, m):
        c, cid = m["content"], m["conversation_id"]
        qty, held = int(c["quantity"]), bool(c.get("held"))
        event = self.db.get(Event, c["event_id"])
        cat = self.db.get(TicketCategory, c["ticket_category_id"])
        if not event or event.status != "published":
            return self.reply(m, "REFUSE", {"reason": "Published event not found", "code": "NOT_FOUND"})
        if not cat or cat.event_id != event.id:
            return self.reply(m, "REFUSE", {"reason": "Ticket category not found", "code": "NOT_FOUND"})
        if qty < 1 or qty > self.MAX_PER_BOOKING:
            return self.reply(m, "REFUSE", {"reason": "Maximum 6 tickets per booking"})
        if now_local() >= event.start_time:
            return self.reply(m, "REFUSE", {"reason": "Booking is closed: the event has already started"})
        if not held and not self._take(cat.id, qty):
            self.bump("refused_sold_out")
            return self.reply(m, "REFUSE", {"reason": "Tickets sold out or not enough left; join the waitlist", "code": "SOLD_OUT"})
        total = money(cat.price * qty)
        b = Booking(user_id=c["user_id"], event_id=event.id, ticket_category_id=cat.id, quantity=qty,
                    total_amount=total, status="confirmed")
        self.db.add(b)
        self.db.flush()
        ref = "SIM-" + secrets.token_hex(8).upper()
        self.db.add(Payment(booking_id=b.id, payment_reference=ref, amount=total, status="success"))
        self.db.flush()
        issued = self.ask("TicketAgent", {"action": "issue", "booking_id": b.id, "quantity": qty}, cid)
        if issued["performative"] != "AGREE":
            raise RuntimeError("Ticket issuing failed: " + str(issued["content"].get("reason")))
        self.bump("bookings_confirmed")
        self.tell("NotificationAgent", {"user_id": b.user_id, "title": "Booking confirmed",
                                        "message": f"Booking #{b.id} for {event.title} is confirmed ({qty} ticket(s), LKR {total}). Simulated payment ref {ref}."}, cid)
        return self.reply(m, "AGREE", {"booking_id": b.id, "event": event.title, "quantity": qty, "amount": str(total),
                                       "payment_reference": ref, "tickets": issued["content"]["tickets"]})

    def _cancel(self, m):
        c, cid = m["content"], m["conversation_id"]
        b = self.db.get(Booking, c["booking_id"])
        if not b or b.user_id != c["user_id"]:
            return self.reply(m, "REFUSE", {"reason": "Booking not found", "code": "NOT_FOUND"})
        if b.status != "confirmed":
            return self.reply(m, "REFUSE", {"reason": "Booking is not active"})
        event = b.event
        if event.status != "cancelled" and now_local() >= event.start_time:
            return self.reply(m, "REFUSE", {"reason": "The event has already started; booking cannot be cancelled"})
        refund = self.refund_amount(b, event)
        b.status, b.refund_amount, b.cancelled_at = "cancelled", refund, now_local()
        for p in self.db.query(Payment).filter_by(booking_id=b.id):
            p.status = "refunded" if refund > 0 else "no_refund"
        self.db.flush()
        self.ask("TicketAgent", {"action": "void", "booking_id": b.id}, cid)
        self._release(b.ticket_category_id, b.quantity)
        self.db.flush()
        self.bump("bookings_cancelled")
        self.tell("NotificationAgent", {"user_id": b.user_id, "title": "Booking cancelled",
                                        "message": f"Booking #{b.id} was cancelled. Refund: LKR {refund}."}, cid)
        self.bus.broadcast(self.name, {"event": "seats_released", "event_id": b.event_id,
                                       "ticket_category_id": b.ticket_category_id, "quantity": b.quantity}, cid)
        return self.reply(m, "AGREE", {"status": "cancelled", "refund_amount": str(refund),
                                       "policy": "100% refund at least 48 hours before the event; no refund inside 48 hours; full refund if the event is cancelled."})

    def _cancel_event(self, m):
        c, cid = m["content"], m["conversation_id"]
        event = self.db.get(Event, c["event_id"])
        if not event or event.status != "cancelled":
            return self.reply(m, "REFUSE", {"reason": "Event must be marked cancelled first"})
        total, count = Decimal("0.00"), 0
        for b in self.db.query(Booking).filter_by(event_id=event.id, status="confirmed").all():
            b.status, b.refund_amount, b.cancelled_at = "cancelled", money(b.total_amount), now_local()
            for p in self.db.query(Payment).filter_by(booking_id=b.id):
                p.status = "refunded"
            self.db.flush()
            self.ask("TicketAgent", {"action": "void", "booking_id": b.id}, cid)
            self.tell("NotificationAgent", {"user_id": b.user_id, "title": f"{event.title} cancelled",
                                            "message": f"The event was cancelled. Booking #{b.id} is refunded in full (LKR {b.refund_amount})."}, cid)
            total += money(b.total_amount)
            count += 1
        self.ask("WaitlistAgent", {"action": "close_event", "event_id": event.id}, cid)        
        self.db.flush()
        self.bump("events_cancelled")
        return self.reply(m, "AGREE", {"bookings_refunded": count, "refunded_total": str(total)})