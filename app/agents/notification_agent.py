"""NotificationAgent: turns INFORM messages about a user into stored notifications."""
from app.agents.base import BaseAgent
from app.agents.bus import register
from app.models import Notification


@register
class NotificationAgent(BaseAgent):
    """Goal: tell the right person what affects them.
    RULES
      N1 Listens to INFORM messages (direct or broadcast) that name a user_id and stores a notification for that user.
      N2 Ignores INFORM events that concern nobody in particular (e.g. seats_released).
      N3 Refuses non-INFORM messages with a reason.
    """
    name = "NotificationAgent"

    def handle(self, m):
        if m["performative"] != "INFORM":
            return self.reply(m, "REFUSE", {"reason": "NotificationAgent only accepts INFORM messages"})
        c = m["content"]
        if "user_id" not in c:
            return None
        self.db.add(Notification(user_id=c["user_id"], title=c.get("title", "EventSphere update"), message=c.get("message", "")))
        self.db.flush()
        self.bump("notifications_sent")
        return self.reply(m, "AGREE", {"notification_recorded": True})