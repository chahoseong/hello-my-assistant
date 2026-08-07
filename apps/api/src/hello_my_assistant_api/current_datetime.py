from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel
from pydantic_ai import ModelRetry


class CurrentDateTime(BaseModel):
    local_datetime: datetime
    timezone: str


def get_current_datetime(timezone: str) -> CurrentDateTime:
    """Get the current local date and time for an IANA time zone.

    Args:
        timezone: An IANA time zone name, such as Asia/Seoul.
    """
    try:
        zone = ZoneInfo(timezone)
    except ZoneInfoNotFoundError as exc:
        raise ModelRetry(f"Unknown IANA time zone: {timezone}") from exc

    return CurrentDateTime(local_datetime=datetime.now(zone), timezone=timezone)
