from datetime import datetime
from typing import Optional


def parse_date(value: str, fmt: str = "%Y-%m-%d") -> Optional[datetime]:
    try:
        return datetime.strptime(value, fmt)
    except (TypeError, ValueError):
        return None
