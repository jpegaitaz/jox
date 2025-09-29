# src/linkedin_mcp_server/tools/company.py
# SPDX-License-Identifier: Apache-2.0
"""
LinkedIn company profile scraping tools with employee data extraction (JOX-hardened).

- Env-only auth (LINKEDIN_COOKIE='li_at=...').
- Safe driver acquisition via drivers.get_or_create_driver_env().
- Accepts company handle or full URL; normalizes to https://www.linkedin.com/company/<handle>/.
- Defensive parsing and PII-safe logging.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List
from urllib.parse import urlparse

from fastmcp import FastMCP
from linkedin_scraper import Company  # type: ignore

from ..drivers import get_or_create_driver_env
from ..error_handler import handle_tool_error

logger = logging.getLogger(__name__)


def _normalize_company_input(company_name_or_url: str) -> str:
    """
    Accept a company handle (e.g., 'anthropic') or a full LinkedIn URL and
    return a canonical company URL: 'https://www.linkedin.com/company/<handle>/'.
    """
    raw = (company_name_or_url or "").strip()
    if not raw:
        raise ValueError("Empty company identifier")

    if raw.startswith("http://") or raw.startswith("https://"):
        u = urlparse(raw)
        if "linkedin.com" not in u.netloc:
            raise ValueError("Only linkedin.com company URLs are supported")
        path = u.path.strip("/")
        parts = path.split("/")
        # Expect patterns like: company/<handle>[/...]
        if len(parts) >= 2 and parts[0] == "company":
            handle = parts[1]
            if not handle:
                raise ValueError("Invalid LinkedIn company URL: missing handle")
            return f"https://www.linkedin.com/company/{handle}/"
        raise ValueError("Unsupported LinkedIn company URL format")
    else:
        handle = raw.strip("/")
        if not handle:
            raise ValueError("Invalid LinkedIn company handle")
        return f"https://www.linkedin.com/company/{handle}/"


def _safe_attr(obj: Any, name: str, default=None):
    try:
        return getattr(obj, name, default)
    except Exception:
        return default


def register_company_tools(mcp: FastMCP) -> None:
    """
    Register all company-related tools with the MCP server.
    """

    @mcp.tool()
    async def get_company_profile(
        company_name: str, get_employees: bool = False
    ) -> Dict[str, Any]:
        """
        Get a specific company's LinkedIn profile.

        Args:
            company_name (str): LinkedIn company handle (e.g., "docker", "anthropic")
                                or a full LinkedIn company URL.
            get_employees (bool): Whether to scrape the company's employees (slower).

        Returns:
            Dict[str, Any]: Structured data from the company's profile.
        """
        try:
            linkedin_url = _normalize_company_input(company_name)
            logger.info(f"Scraping company: {linkedin_url}")
            if get_employees:
                logger.info("Fetching employees may take longer...")

            # Authenticated driver via env-only cookie
            driver = get_or_create_driver_env()

            # Be polite to avoid hammering
            time.sleep(0.4)

            company = Company(
                linkedin_url,
                driver=driver,
                get_employees=get_employees,
                close_on_complete=False,
            )

            # Showcase pages
            showcase_pages: List[Dict[str, Any]] = []
            for page in _safe_attr(company, "showcase_pages", []) or []:
                showcase_pages.append(
                    {
                        "name": _safe_attr(page, "name"),
                        "linkedin_url": _safe_attr(page, "linkedin_url"),
                        "followers": _safe_attr(page, "followers"),
                    }
                )

            # Affiliated companies
            affiliated_companies: List[Dict[str, Any]] = []
            for aff in _safe_attr(company, "affiliated_companies", []) or []:
                affiliated_companies.append(
                    {
                        "name": _safe_attr(aff, "name"),
                        "linkedin_url": _safe_attr(aff, "linkedin_url"),
                        "followers": _safe_attr(aff, "followers"),
                    }
                )

            result: Dict[str, Any] = {
                "linkedin_url": linkedin_url,
                "name": _safe_attr(company, "name"),
                "about_us": _safe_attr(company, "about_us"),
                "website": _safe_attr(company, "website"),
                "phone": _safe_attr(company, "phone"),
                "headquarters": _safe_attr(company, "headquarters"),
                "founded": _safe_attr(company, "founded"),
                "industry": _safe_attr(company, "industry"),
                "company_type": _safe_attr(company, "company_type"),
                "company_size": _safe_attr(company, "company_size"),
                "specialties": _safe_attr(company, "specialties"),
                "showcase_pages": showcase_pages,
                "affiliated_companies": affiliated_companies,
                "headcount": _safe_attr(company, "headcount"),
            }

            if get_employees:
                employees = _safe_attr(company, "employees")
                if employees:
                    result["employees"] = employees

            return result

        except Exception as e:
            return handle_tool_error(e, "get_company_profile")
