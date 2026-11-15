"""Time helpers.

All datetimes in EventSphere are stored as *naive local venue time* (what the user typed in the
browser's datetime-local field). The server clock runs in UTC on Render, so 'now' must be shifted
by APP_TZ_OFFSET_MINUTES (default 330 = Sri Lanka, UTC+05:30) before comparing.
"""
import os
from datetime import datetime, timedelta, timezone

TZ_OFFSET_MINUTES = int(os.getenv("APP_TZ_OFFSET_MINUTES", "330"))


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def now_local() -> datetime:
    return utc_now() + timedelta(minutes=TZ_OFFSET_MINUTES)
