import json, secrets
from datetime import datetime, timedelta
from decimal import Decimal
from sqlalchemy import and_
from app.models import (Venue, Event, TicketCategory, Ticket, Booking, VenueHire,
                        WaitlistEntry, Notification, AgentState)
from app.agents.bus import AgentBus

class BaseAgent:
    name = "BaseAgent"
    def __init__(self, db):
        self.db, self.bus = db, AgentBus(db)
        row = db.query(AgentState).filter_by(agent_name=self.name).first()
        self.state = json.loads(row.state_json) if row else {}
        if not row:
            db.add(AgentState(agent_name=self.name, state_json="{}")); db.commit()
    def save(self):
        row = self.db.query(AgentState).filter_by(agent_name=self.name).first()
        row.state_json = json.dumps(self.state); row.updated_at = datetime.utcnow(); self.db.commit()
    def msg(self, to, perf, content, cid=None):
        return self.bus.send(self.name, to, perf, content, cid)

class VenueAgent(BaseAgent):
    name = "VenueAgent"
    BUFFER_MINUTES = 30
    def check_slot(self, venue_id, start, end, exclude_event_id=None):
        venue = self.db.query(Venue).filter_by(id=venue_id, is_available=True).first()
        if not venue:
            return {"decision":"REFUSE","reason":"Venue not found or unavailable"}
        buffer = timedelta(minutes=self.BUFFER_MINUTES)
        q = self.db.query(Event).filter(Event.venue_id==venue_id,
            Event.status!="cancelled", Event.start_time < end+buffer,
            Event.end_time > start-buffer)
        if exclude_event_id: q=q.filter(Event.id != exclude_event_id)
        if q.first(): return {"decision":"REFUSE","reason":"Venue clash or 30-minute turnaround buffer"}
        return {"decision":"AGREE","reason":"Venue slot is available"}
    def decide_hire(self, hire):
        venue = self.db.query(Venue).filter_by(id=hire.venue_id, is_available=True).first()
        if not venue: return {"decision":"REFUSE","reason":"Venue is not open for private hire"}
        if hire.guest_count > venue.capacity:
            return {"decision":"PROPOSE","reason":"Guest count exceeds venue capacity",
                    "alternatives":[{"venue_id":v.id,"venue":v.name} for v in self.db.query(Venue).filter(Venue.capacity>=hire.guest_count, Venue.is_available==True, Venue.id!=venue.id).limit(3)]}
        clash = self.check_slot(hire.venue_id, hire.start_time, hire.end_time)
        if clash["decision"] != "AGREE":
            alternatives=[]
            for v in self.db.query(Venue).filter(Venue.is_available==True, Venue.capacity>=hire.guest_count, Venue.id!=venue.id).limit(3):
                alternatives.append({"venue_id":v.id,"venue":v.name,"reason":"Alternative available venue; confirm calendar with administrator"})
            return {"decision":"PROPOSE","reason":clash["reason"],"alternatives":alternatives}
        hours=Decimal(str((hire.end_time-hire.start_time).total_seconds()/3600))
        return {"decision":"AGREE","reason":"Routine hire request accepted","price":str(hours*venue.price_per_hour)}
    def handle(self, message):
        c=message["content"]
        return self.msg(message["sender"],"INFORM",self.check_slot(c["venue_id"],datetime.fromisoformat(c["start"]),datetime.fromisoformat(c["end"])),message["conversation_id"])

class BookingAgent(BaseAgent):
    name = "BookingAgent"
    MAX_PER_BOOKING=6
    REFUND_HOURS=48
    def assess(self, category, quantity):
        if quantity > self.MAX_PER_BOOKING: return {"decision":"REFUSE","reason":"Maximum 6 tickets per booking"}
        if not category or category.available_quantity < quantity: return {"decision":"REFUSE","reason":"Insufficient ticket inventory"}
        return {"decision":"AGREE","reason":"Inventory and quantity rules passed"}
    def refund(self, booking, event):
        if event.status=="cancelled": return booking.total_amount
        hours=(event.start_time-datetime.utcnow()).total_seconds()/3600
        return booking.total_amount if hours>=self.REFUND_HOURS else Decimal("0.00")
    def handle(self, message):
        return self.msg(message["sender"],"INFORM",{"rule":"max 6 tickets; check inventory atomically"},message["conversation_id"])

class TicketAgent(BaseAgent):
    name = "TicketAgent"
    def issue(self, booking):
        made=[]
        for _ in range(booking.quantity):
            token=secrets.token_urlsafe(32)
            ticket=Ticket(booking_id=booking.id,qr_code=token,status="valid")
            self.db.add(ticket); made.append(ticket)
        self.db.flush()
        self.state["issued"] = self.state.get("issued",0)+len(made); self.save()
        return made
    def check_in(self, token, event_id):
        ticket=self.db.query(Ticket).filter_by(qr_code=token).with_for_update().first()
        if not ticket: return {"admitted":False,"reason":"Unknown ticket"}
        booking=ticket.booking
        if booking.event_id != event_id: return {"admitted":False,"reason":"Ticket belongs to another event"}
        if booking.status != "confirmed" or ticket.status != "valid": return {"admitted":False,"reason":"Ticket is cancelled or invalid"}
        if ticket.checked_in: 
            self.state["repeat_scans"]=self.state.get("repeat_scans",0)+1; self.save()
            return {"admitted":False,"reason":"Already used"}
        event=booking.event
        now=datetime.utcnow()
        if now < event.start_time-timedelta(hours=2) or now > event.end_time+timedelta(hours=2):
            return {"admitted":False,"reason":"Outside check-in time"}
        ticket.checked_in=True; ticket.checked_in_at=now
        self.state["successful_checkins"]=self.state.get("successful_checkins",0)+1
        self.save(); self.db.commit()
        return {"admitted":True,"reason":"Admit","ticket_id":ticket.id}
    def handle(self, message):
        return self.msg(message["sender"],"INFORM",{"rule":"unique unguessable token; one admission only"},message["conversation_id"])

class WaitlistAgent(BaseAgent):
    name = "WaitlistAgent"
    HOLD_MINUTES=10
    def offer_next(self, event_id, category_id, available):
        entry=self.db.query(WaitlistEntry).filter_by(event_id=event_id,ticket_category_id=category_id,status="waiting").order_by(WaitlistEntry.created_at).first()
        if not entry or entry.quantity>available: return None
        entry.status="offered"; entry.offered_at=datetime.utcnow(); entry.expires_at=datetime.utcnow()+timedelta(minutes=self.HOLD_MINUTES)
        self.db.commit()
        self.msg("NotificationAgent","INFORM",{"user_id":entry.user_id,"title":"Tickets available","message":f"Your {entry.quantity}-ticket offer expires in {self.HOLD_MINUTES} minutes."})
        self.state["offers"] = self.state.get("offers",0)+1; self.save()
        return entry
    def expire_sweep(self):
        now=datetime.utcnow()
        expired=self.db.query(WaitlistEntry).filter_by(status="offered").filter(WaitlistEntry.expires_at<=now).all()
        for e in expired:
            e.status="expired"
            self.msg("NotificationAgent","INFORM",{"user_id":e.user_id,"title":"Ticket offer expired","message":"Your ticket hold expired; you remain eligible for a later offer."})
        self.db.commit()
        self.state["expired_holds"]=self.state.get("expired_holds",0)+len(expired); self.save()
        # Re-offer any available seats to the next eligible entry.
        for e in expired:
            cat=self.db.query(TicketCategory).filter_by(id=e.ticket_category_id).first()
            if cat and cat.available_quantity: self.offer_next(e.event_id,e.ticket_category_id,cat.available_quantity)
        return len(expired)
    def handle(self, message):
        if message["performative"]=="INFORM": self.state["informs_seen"]=self.state.get("informs_seen",0)+1; self.save()
        return self.msg(message["sender"],"AGREE",{"received":True},message["conversation_id"])

class NotificationAgent(BaseAgent):
    name = "NotificationAgent"
    def notify(self, user_id, title, message):
        self.db.add(Notification(user_id=user_id,title=title,message=message))
        self.db.commit()
        self.state["notifications_sent"]=self.state.get("notifications_sent",0)+1; self.save()
    def handle(self, message):
        c=message["content"]
        if "user_id" in c: self.notify(c["user_id"],c.get("title","EventSphere update"),c.get("message",""))
        return self.msg(message["sender"],"AGREE",{"notification_recorded":True},message["conversation_id"])
