import os
from datetime import datetime, timedelta, timezone

TZ_OFFSET_MINUTES = int(os.getenv("APP_TZ_OFFSET_MINUTES", "330"))


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def now_local() -> datetime:
    return utc_now() + timedelta(minutes=TZ_OFFSET_MINUTES)
