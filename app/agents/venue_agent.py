"""VenueAgent: keeps venue calendars free of clashes and decides private hire."""
import json
from datetime import datetime, time, timedelta
from decimal import Decimal
from app.agents.base import BaseAgent, iso, money
from app.agents.bus import register
from app.models import Event, User, Venue, VenueHire
from app.timeutil import now_local


@register
class VenueAgent(BaseAgent):
    """Goal: keep every venue's calendar free of clashes.
    RULES
      V1 Refuse a slot if the venue is missing/unavailable, if end<=start or start is in the past.
      V2 Refuse a slot that overlaps another event or confirmed hire, including a 30-minute turnaround buffer.
      V3 Hire: refuse/propose if the venue is closed for hire; propose bigger venues if guests > capacity.
      V4 Hire clash: PROPOSE alternative time slots at the same venue and free alternative venues.
      V5 Routine hire (<=6 h, between 08:00 and 22:00, >=24 h notice, fits capacity) is AGREEd automatically.
      V6 Any other feasible hire is escalated to an administrator (INFORM decision=ESCALATE).
      V7 Hire price = duration in hours x venue hourly rate.
    """
    name = "VenueAgent"
    BUFFER_MINUTES = 30
    ROUTINE_MAX_HOURS = 6
    OPEN_HOUR, CLOSE_HOUR = 8, 22
    MIN_LEAD_HOURS = 24

    # reasoning helpers
    def _clash(self, venue_id, start, end, exclude_event_id=None, exclude_hire_id=None):
        buf = timedelta(minutes=self.BUFFER_MINUTES)
        q = self.db.query(Event).filter(Event.venue_id == venue_id, Event.status != "cancelled",
                                        Event.start_time < end + buf, Event.end_time > start - buf)
        if exclude_event_id:
            q = q.filter(Event.id != exclude_event_id)
        if q.first():
            return "Venue clash with another event or the 30-minute turnaround buffer"
        h = self.db.query(VenueHire).filter(VenueHire.venue_id == venue_id, VenueHire.status == "confirmed",
                                            VenueHire.start_time < end + buf, VenueHire.end_time > start - buf)
        if exclude_hire_id:
            h = h.filter(VenueHire.id != exclude_hire_id)
        if h.first():
            return "Venue clash with a confirmed private hire or the 30-minute turnaround buffer"
        return None

    def _slot_decision(self, venue_id, start, end, exclude_event_id=None, exclude_hire_id=None):
        venue = self.db.query(Venue).filter_by(id=venue_id, is_available=True).first()
        if not venue:
            return "REFUSE", "Venue not found or unavailable"
        if end <= start:
            return "REFUSE", "End time must be after start time"
        if start <= now_local():
            return "REFUSE", "Start time is in the past"
        clash = self._clash(venue_id, start, end, exclude_event_id, exclude_hire_id)
        if clash:
            return "REFUSE", clash
        return "AGREE", "Venue slot is available"

    def _price(self, venue, start, end):
        hours = Decimal(str((end - start).total_seconds())) / Decimal(3600)
        return money(hours * venue.price_per_hour)

    def _alt_venues(self, venue, hire, need_free=True):
        out = []
        q = self.db.query(Venue).filter(Venue.is_available == True, Venue.open_for_hire == True,  # noqa: E712
                                        Venue.capacity >= hire.guest_count, Venue.id != venue.id).order_by(Venue.capacity)
        for v in q:
            if need_free and self._clash(v.id, hire.start_time, hire.end_time):
                continue
            out.append({"type": "venue", "venue_id": v.id, "venue": v.name, "capacity": v.capacity,
                        "start": iso(hire.start_time), "end": iso(hire.end_time),
                        "price": str(self._price(v, hire.start_time, hire.end_time))})
            if len(out) == 3:
                break
        return out

    def _alt_slots(self, venue, hire, limit=3):
        dur, now, found = hire.end_time - hire.start_time, now_local(), []
        day0 = hire.start_time.replace(hour=0, minute=0, second=0, microsecond=0)
        for d in range(-2, 8):
            for hr in range(self.OPEN_HOUR, self.CLOSE_HOUR):
                s = day0 + timedelta(days=d, hours=hr)
                e = s + dur
                if s == hire.start_time or s < now + timedelta(hours=self.MIN_LEAD_HOURS):
                    continue
                if e.date() != s.date() or e.time() > time(self.CLOSE_HOUR, 0):
                    continue
                if self._clash(venue.id, s, e):
                    continue
                found.append((abs((s - hire.start_time).total_seconds()), s, e))
        found.sort(key=lambda x: x[0])
        return [{"type": "time", "venue_id": venue.id, "venue": venue.name, "start": iso(s), "end": iso(e),
                 "price": str(self._price(venue, s, e))} for _, s, e in found[:limit]]

    def _decide_hire(self, hire, venue):
        if not venue:
            return {"decision": "REFUSE", "reason": "Venue not found"}
        if hire.end_time <= hire.start_time:
            return {"decision": "REFUSE", "reason": "End time must be after start time"}
        if hire.start_time <= now_local():
            return {"decision": "REFUSE", "reason": "Start time is in the past"}
        if not venue.is_available or not venue.open_for_hire:
            alts = self._alt_venues(venue, hire)
            if alts:
                return {"decision": "PROPOSE", "reason": "This venue is not open for private hire; these venues are free at your time", "alternatives": alts}
            return {"decision": "REFUSE", "reason": "This venue is not open for private hire and no alternative venue is free"}
        if hire.guest_count > venue.capacity:
            alts = self._alt_venues(venue, hire)
            if alts:
                return {"decision": "PROPOSE", "reason": f"Guest count exceeds venue capacity ({venue.capacity})", "alternatives": alts}
            return {"decision": "REFUSE", "reason": f"Guest count exceeds venue capacity ({venue.capacity}) and no larger venue is free"}
        clash = self._clash(venue.id, hire.start_time, hire.end_time, exclude_hire_id=hire.id)
        if clash:
            alts = self._alt_slots(venue, hire) + self._alt_venues(venue, hire)
            if alts:
                return {"decision": "PROPOSE", "reason": clash, "alternatives": alts}
            return {"decision": "REFUSE", "reason": clash + "; no alternatives found in the next week"}
        price = str(self._price(venue, hire.start_time, hire.end_time))
        hours = (hire.end_time - hire.start_time).total_seconds() / 3600
        reasons = []
        if hours > self.ROUTINE_MAX_HOURS:
            reasons.append(f"longer than {self.ROUTINE_MAX_HOURS} hours")
        if hire.start_time.time() < time(self.OPEN_HOUR, 0) or hire.end_time.date() != hire.start_time.date() \
                or hire.end_time.time() > time(self.CLOSE_HOUR, 0):
            reasons.append(f"outside {self.OPEN_HOUR:02d}:00-{self.CLOSE_HOUR:02d}:00")
        if hire.start_time < now_local() + timedelta(hours=self.MIN_LEAD_HOURS):
            reasons.append(f"less than {self.MIN_LEAD_HOURS} hours notice")
        if reasons:
            return {"decision": "ESCALATE", "reason": "Needs administrator approval: " + ", ".join(reasons), "price": price}
        return {"decision": "AGREE", "reason": "Routine hire request accepted automatically", "price": price}

    # --- message handler
    def handle(self, m):
        if m["performative"] != "REQUEST":
            return None
        c, a = m["content"], m["content"].get("action")
        if a == "check_slot":
            decision, reason = self._slot_decision(c["venue_id"], datetime.fromisoformat(c["start"]),
                                                   datetime.fromisoformat(c["end"]), c.get("exclude_event_id"),
                                                   c.get("exclude_hire_id"))
            self.bump("slots_" + decision.lower())
            return self.reply(m, decision, {"reason": reason, "code": "CLASH" if decision == "REFUSE" else None})
        if a == "hire":
            return self._hire(m)
        if a == "admin_decision":
            return self._admin_decision(m)
        return self.reply(m, "REFUSE", {"reason": f"Unknown action '{a}'"})

    def _hire(self, m):
        cid, hire = m["conversation_id"], self.db.get(VenueHire, m["content"]["hire_id"])
        venue = self.db.get(Venue, hire.venue_id)
        d = self._decide_hire(hire, venue)
        status = {"AGREE": "confirmed", "PROPOSE": "alternatives_offered", "REFUSE": "rejected", "ESCALATE": "escalated"}[d["decision"]]
        hire.status, hire.decision_reason = status, d["reason"]
        hire.alternatives_json = json.dumps(d.get("alternatives", []))
        hire.quoted_price = Decimal(d["price"]) if d.get("price") else 0
        self.db.flush()
        self.bump("hires_" + d["decision"].lower())
        msg = d["reason"] + (f" Price: LKR {d['price']}." if d.get("price") else "")
        self.tell("NotificationAgent", {"user_id": hire.user_id, "title": f"Venue hire #{hire.id}: {status.replace('_', ' ')}", "message": msg}, cid)
        if d["decision"] == "ESCALATE":
            for admin in self.db.query(User).filter_by(role="admin", is_active=True):
                self.tell("NotificationAgent", {"user_id": admin.id, "title": "Venue hire needs review",
                                                "message": f"Request #{hire.id} for {venue.name}: {d['reason']}"}, cid)
        perf = "INFORM" if d["decision"] == "ESCALATE" else d["decision"]
        return self.reply(m, perf, {**d, "hire_id": hire.id, "status": status})

    def _admin_decision(self, m):
        c, cid = m["content"], m["conversation_id"]
        hire = self.db.get(VenueHire, c["hire_id"])
        if not hire or hire.status != "escalated":
            return self.reply(m, "REFUSE", {"reason": "Escalated hire not found", "code": "NOT_FOUND"})
        if c["decision"] == "confirmed":
            clash = self._clash(hire.venue_id, hire.start_time, hire.end_time, exclude_hire_id=hire.id)
            if clash:
                return self.reply(m, "REFUSE", {"reason": clash, "code": "CLASH"})
            venue = self.db.get(Venue, hire.venue_id)
            hire.quoted_price = self._price(venue, hire.start_time, hire.end_time)
        hire.status = c["decision"]
        hire.decision_reason = f"Administrator {c['decision']} the request" + (f": {c['note']}" if c.get("note") else "")
        self.db.flush()
        self.bump("admin_" + c["decision"])
        self.tell("NotificationAgent", {"user_id": hire.user_id, "title": f"Venue hire #{hire.id} {c['decision']}", "message": hire.decision_reason}, cid)
        return self.reply(m, "AGREE", {"status": hire.status, "reason": hire.decision_reason})