# jox/mcp/servers/linkedin_mcp_server/drivers/__init__.py

"""
Driver management package for LinkedIn scraping (JOX).
Re-export chrome helpers and provide env-based convenience.
"""

from __future__ import annotations
from typing import Optional
from .chrome import (
    create_chrome_driver,
    create_temporary_chrome_driver,
    get_or_create_driver,
    get_active_driver,
    close_all_drivers,
)
from ..config.secrets import Secrets  # env-only cookie accessor


def get_or_create_driver_env():
    """
    Convenience: read LINKEDIN_COOKIE (li_at=...) via Secrets and return an
    authenticated Chrome WebDriver, creating it if needed.
    """
    cookie = Secrets.get_cookie()  # raises if missing
    return get_or_create_driver(cookie)


__all__ = [
    "create_chrome_driver",
    "create_temporary_chrome_driver",
    "get_or_create_driver",
    "get_or_create_driver_env",   # some tools import this
    "get_active_driver",
    "close_all_drivers",
]
