# src/linkedin_mcp_server/tools/person.py
# SPDX-License-Identifier: Apache-2.0
"""
LinkedIn person profile scraping tools with structured data extraction (JOX-hardened).

- Env-only auth (LINKEDIN_COOKIE='li_at=...').
- Safe driver acquisition via drivers.get_or_create_driver_env().
- Accepts username or full URL, normalizes to https://www.linkedin.com/in/<handle>/.
- Defensive parsing: tolerate missing fields / library changes.
- Clear, PII-safe error handling.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List
from urllib.parse import urlparse

from fastmcp import FastMCP
from linkedin_scraper import Person  # type: ignore

from ..drivers import get_or_create_driver_env
from ..error_handler import handle_tool_error

logger = logging.getLogger(__name__)


def _normalize_profile_input(linkedin_username_or_url: str) -> str:
    """
    Accept either a username (e.g., 'stickerdaniel') or a full LinkedIn URL and
    return a canonical profile URL like 'https://www.linkedin.com/in/<handle>/'.
    """
    raw = (linkedin_username_or_url or "").strip()
    if not raw:
        raise ValueError("Empty LinkedIn identifier")

    # If it's a URL, verify it's linkedin.com and extract the /in/<handle> path.
    if raw.startswith("http://") or raw.startswith("https://"):
        u = urlparse(raw)
        if "linkedin.com" not in u.netloc:
            raise ValueError("Only linkedin.com profiles are supported")
        # Allow both /in/<handle> and /pub/ legacy formats; prefer /in/
        path = u.path.strip("/")
        # Common patterns: 'in/<handle>', 'in/<handle>/', 'pub/<handle>/...'
        parts = path.split("/")
        if len(parts) >= 2 and parts[0] in {"in", "pub"}:
            handle = parts[1]
            if not handle:
                raise ValueError("Invalid LinkedIn profile URL: missing handle")
            return f"https://www.linkedin.com/in/{handle}/"
        raise ValueError("Unsupported LinkedIn profile URL format")
    else:
        # Treat as username/handle
        handle = raw.replace("@", "").strip("/")
        if not handle:
            raise ValueError("Invalid LinkedIn username")
        return f"https://www.linkedin.com/in/{handle}/"


def _safe_attr(obj: Any, name: str, default=None):
    try:
        return getattr(obj, name, default)
    except Exception:
        return default


def register_person_tools(mcp: FastMCP) -> None:
    """
    Register person-related tools with the MCP server.
    """

    @mcp.tool()
    async def get_person_profile(linkedin_username: str) -> Dict[str, Any]:
        """
        Get a specific person's LinkedIn profile.

        Args:
            linkedin_username (str): LinkedIn username (e.g., "stickerdaniel")
                                     or a full profile URL (https://www.linkedin.com/in/handle/)

        Returns:
            Dict[str, Any]: Structured data from the person's profile
        """
        try:
            profile_url = _normalize_profile_input(linkedin_username)
            logger.info(f"Scraping profile: {profile_url}")

            # Obtain (or create) an authenticated driver using env-only cookie
            driver = get_or_create_driver_env()

            # Be a bit polite to avoid hammering
            time.sleep(0.5)

            person = Person(profile_url, driver=driver, close_on_complete=False)

            # Normalize experiences
            raw_exps = _safe_attr(person, "experiences", []) or []
            experiences: List[Dict[str, Any]] = []
            for exp in raw_exps:
                experiences.append(
                    {
                        "position_title": _safe_attr(exp, "position_title"),
                        "company": _safe_attr(exp, "institution_name"),
                        "from_date": _safe_attr(exp, "from_date"),
                        "to_date": _safe_attr(exp, "to_date"),
                        "duration": _safe_attr(exp, "duration"),
                        "location": _safe_attr(exp, "location"),
                        "description": _safe_attr(exp, "description"),
                    }
                )

            # Normalize education
            raw_edu = _safe_attr(person, "educations", []) or []
            educations: List[Dict[str, Any]] = []
            for edu in raw_edu:
                educations.append(
                    {
                        "institution": _safe_attr(edu, "institution_name"),
                        "degree": _safe_attr(edu, "degree"),
                        "from_date": _safe_attr(edu, "from_date"),
                        "to_date": _safe_attr(edu, "to_date"),
                        "description": _safe_attr(edu, "description"),
                    }
                )

            # Interests
            raw_interests = _safe_attr(person, "interests", []) or []
            interests: List[str] = []
            for it in raw_interests:
                title = _safe_attr(it, "title")
                if title:
                    interests.append(title)

            # Accomplishments
            raw_acc = _safe_attr(person, "accomplishments", []) or []
            accomplishments: List[Dict[str, Any]] = []
            for acc in raw_acc:
                accomplishments.append(
                    {
                        "category": _safe_attr(acc, "category"),
                        "title": _safe_attr(acc, "title"),
                    }
                )

            # Contacts (publicly visible connections)
            raw_contacts = _safe_attr(person, "contacts", []) or []
            contacts: List[Dict[str, Any]] = []
            for c in raw_contacts:
                contacts.append(
                    {
                        "name": _safe_attr(c, "name"),
                        "occupation": _safe_attr(c, "occupation"),
                        "url": _safe_attr(c, "url"),
                    }
                )

            return {
                "profile_url": profile_url,
                "name": _safe_attr(person, "name"),
                "about": _safe_attr(person, "about"),
                "experiences": experiences,
                "educations": educations,
                "interests": interests,
                "accomplishments": accomplishments,
                "contacts": contacts,
                "company": _safe_attr(person, "company"),
                "job_title": _safe_attr(person, "job_title"),
                "open_to_work": bool(_safe_attr(person, "open_to_work", False)),
            }

        except Exception as e:
            # Standardized error response (never leaks secrets)
            return handle_tool_error(e, "get_person_profile")
