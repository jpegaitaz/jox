from __future__ import annotations
from datetime import datetime, timezone

def iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()

def today_compact() -> str:
    return datetime.now().strftime("%Y-%m-%d")
