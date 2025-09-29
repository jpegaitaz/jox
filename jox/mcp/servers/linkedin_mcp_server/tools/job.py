# src/linkedin_mcp_server/tools/job.py
# SPDX-License-Identifier: Apache-2.0
"""
LinkedIn job scraping tools with search and detail extraction capabilities (JOX-hardened).

- Env-only auth (LINKEDIN_COOKIE='li_at=...').
- Safe driver acquisition via drivers.get_or_create_driver_env().
- Input hygiene: accept job ID or full URL, normalize, and validate the host.
- PII-safe logging and robust error handling.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List
from urllib.parse import urlparse, parse_qs

from fastmcp import FastMCP
from linkedin_scraper import Job, JobSearch  # type: ignore

from ..drivers import get_or_create_driver_env
from ..error_handler import (
    handle_tool_error,
    handle_tool_error_list,
)

logger = logging.getLogger(__name__)


# -----------------------------
# Helpers
# -----------------------------
def _normalize_job_id_or_url(job_id_or_url: str) -> str:
    """
    Accepts a LinkedIn job ID (e.g., '4252026496') OR a full URL,
    returns a canonical job URL: 'https://www.linkedin.com/jobs/view/<id>/'.
    Raises ValueError for unsupported/non-linkedin hosts or missing ID.
    """
    raw = (job_id_or_url or "").strip()
    if not raw:
        raise ValueError("Empty job identifier")

    if raw.startswith("http://") or raw.startswith("https://"):
        u = urlparse(raw)
        if "linkedin.com" not in u.netloc:
            raise ValueError("Only linkedin.com job URLs are supported")

        # Try to extract ID from common patterns:
        # /jobs/view/<id>/..., or query params (?currentJobId=...), or /jobs/view/?currentJobId=<id>
        parts = [p for p in u.path.split("/") if p]
        id_candidate = None
        if len(parts) >= 3 and parts[0] == "jobs" and parts[1] == "view":
            # e.g., /jobs/view/4252026496/
            id_candidate = parts[2]
        if not id_candidate:
            qs = parse_qs(u.query or "")
            id_vals = qs.get("currentJobId") or qs.get("jobId") or qs.get("id")
            if id_vals and id_vals[0]:
                id_candidate = id_vals[0]

        if not (id_candidate and id_candidate.isdigit()):
            raise ValueError("Could not extract a valid LinkedIn job ID from the URL")

        return f"https://www.linkedin.com/jobs/view/{id_candidate}/"

    # Otherwise treat input as a job id
    if not raw.isdigit():
        raise ValueError("Job ID must be numeric or provide a valid LinkedIn job URL")
    return f"https://www.linkedin.com/jobs/view/{raw}/"


# -----------------------------
# Tool registration
# -----------------------------
def register_job_tools(mcp: FastMCP) -> None:
    """
    Register all job-related tools with the MCP server.
    """

    @mcp.tool()
    async def get_job_details(job_id: str) -> Dict[str, Any]:
        """
        Get job details for a specific posting.

        Args:
            job_id (str): LinkedIn job ID (e.g., "4252026496") OR a full LinkedIn job URL.

        Returns:
            Dict[str, Any]: Structured job data (title, company, location, dates, description, etc.)
        """
        try:
            job_url = _normalize_job_id_or_url(job_id)
            logger.info(f"Scraping job: {job_url}")

            driver = get_or_create_driver_env()

            # Be gentle on navigation
            time.sleep(0.4)

            job = Job(job_url, driver=driver, close_on_complete=False)
            # linkedin_scraper Job has a .to_dict(); keep as-is for compatibility
            data = job.to_dict()
            # Ensure we include the canonical URL we scraped
            if isinstance(data, dict) and "job_url" not in data:
                data["job_url"] = job_url
            return data

        except Exception as e:
            return handle_tool_error(e, "get_job_details")

    @mcp.tool()
    async def search_jobs(search_term: str) -> List[Dict[str, Any]]:
        """
        Search for jobs on LinkedIn using a free-text search term.

        Args:
            search_term (str): e.g., "ML Engineer Switzerland remote fintech"

        Returns:
            List[Dict[str, Any]]: List of job dicts (as returned by linkedin_scraper)
        """
        try:
            term = (search_term or "").strip()
            if not term:
                raise ValueError("Search term cannot be empty")

            driver = get_or_create_driver_env()

            logger.info(f"Searching jobs: {term}")
            # scrape=False → fast results (IDs, titles, companies, locations)
            js = JobSearch(driver=driver, close_on_complete=False, scrape=False)

            # The library's API is `search(term)`; it handles pagination internally where supported.
            jobs = js.search(term) or []

            # Convert job objects to dicts (library provides to_dict)
            results = []
            for j in jobs:
                try:
                    d = j.to_dict()
                    # add canonical job url if missing
                    if isinstance(d, dict) and "job_url" not in d:
                        jid = d.get("job_id") or d.get("id")
                        if jid and str(jid).isdigit():
                            d["job_url"] = f"https://www.linkedin.com/jobs/view/{jid}/"
                    results.append(d)
                except Exception:
                    # Be robust; skip items that fail to serialize
                    continue

            return results

        except Exception as e:
            return handle_tool_error_list(e, "search_jobs")

    @mcp.tool()
    async def get_recommended_jobs() -> List[Dict[str, Any]]:
        """
        Get personalized recommended jobs from LinkedIn for the authenticated user.

        Returns:
            List[Dict[str, Any]]: List of recommended job dicts (may be empty)
        """
        try:
            driver = get_or_create_driver_env()

            logger.info("Getting recommended jobs")
            # scrape=True with scrape_recommended_jobs to fetch the personalized feed
            js = JobSearch(
                driver=driver,
                close_on_complete=False,
                scrape=True,
                scrape_recommended_jobs=True,
            )

            # The library may expose `recommended_jobs`; normalize defensively
            recs = []
            items = getattr(js, "recommended_jobs", []) or []
            for j in items:
                try:
                    d = j.to_dict()
                    if isinstance(d, dict) and "job_url" not in d:
                        jid = d.get("job_id") or d.get("id")
                        if jid and str(jid).isdigit():
                            d["job_url"] = f"https://www.linkedin.com/jobs/view/{jid}/"
                    recs.append(d)
                except Exception:
                    continue

            return recs

        except Exception as e:
            return handle_tool_error_list(e, "get_recommended_jobs")
