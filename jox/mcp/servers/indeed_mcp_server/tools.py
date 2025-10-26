# jox/mcp/servers/indeed_mcp_server/tools.py
from __future__ import annotations

import asyncio
import logging
import urllib.parse
from typing import List, Dict, Optional
from urllib.parse import urlparse, parse_qs

from bs4 import BeautifulSoup

from .config.settings import SETTINGS
from .http import http_get, base_domain_for_country
from .parser import parse_search_list

logger = logging.getLogger(__name__)


# ---------------------------
# Search helpers
# ---------------------------
def _search_url(query: str, location: str, days: int, start: int, domain: str) -> str:
    params = {
        "q": query,
        "l": location,
        "fromage": str(days),  # posted within N days
        "sort": "date",
        "start": str(start),
    }
    return f"https://{domain}/jobs?{urllib.parse.urlencode(params)}"


def _one_pass(query: str, location: str, days: int, limit: int, domain: str) -> List[Dict]:
    results: List[Dict] = []
    seen = set()
    pages = 0

    while pages < SETTINGS.max_pages and len(results) < limit:
        url = _search_url(query, location, days, start=pages * 10, domain=domain)
        html = http_get(url, country=domain)  # keep headers/locale aligned with domain
        if not html:
            break

        batch = parse_search_list(html, base_url=f"https://{domain}")
        new = []
        for j in batch:
            key = j.get("url") or j.get("job_url") or j.get("id")
            if key and key not in seen:
                seen.add(key)
                new.append(j)

        results.extend(new)
        if not new:
            break

        pages += 1

    return results[:limit]


def search_jobs(
    query: str,
    location: str,
    days: int,
    limit: int,
    country: Optional[str] = None,
) -> List[Dict]:
    """
    Try inferred domain first (e.g., indeed.ch for 'Switzerland'), then fallback to .com.
    Also widen 'days' if the narrow window returns nothing.
    """
    domain_pref = base_domain_for_country(country or location)
    logger.info(
        "Indeed search: q='%s', l='%s', days=%s, limit=%s (domain=%s)",
        query, location, days, limit, domain_pref
    )

    # Pass 1: inferred domain with requested 'days'
    results = _one_pass(query, location, days, limit, domain_pref)
    if results:
        return results

    # Pass 2: inferred domain, widen days
    for d in (14, 30):
        logger.info("No hits; widening window to %s days on %s", d, domain_pref)
        results = _one_pass(query, location, d, limit, domain_pref)
        if results:
            return results

    # Pass 3: fallback to .com (with original + widened windows)
    fallback_dom = "www.indeed.com"
    if domain_pref != fallback_dom:
        logger.info("Falling back to %s", fallback_dom)
        results = _one_pass(query, location, days, limit, fallback_dom)
        if results:
            return results
        for d in (14, 30):
            logger.info("No hits on .com; widening to %s days", d)
            results = _one_pass(query, location, d, limit, fallback_dom)
            if results:
                return results

    return []


# ---------------------------
# Detail helpers
# ---------------------------
def _normalize_job_url(job_id_or_url: str, country: Optional[str]) -> str:
    """
    - If given a full URL, return as-is.
    - If given a job key (jk), build a stable view URL on the proper domain.
    """
    if job_id_or_url.startswith("http"):
        return job_id_or_url
    dom = base_domain_for_country(country)
    return f"https://{dom}/viewjob?jk={job_id_or_url}"


def get_job_details(job_id_or_url: str, country: Optional[str] = None) -> Dict:
    """
    Fetch a single job page and extract details.
    Works with either a full URL or a jobkey (`jk`).
    """
    url = _normalize_job_url(job_id_or_url, country)
    html = http_get(url, country=country)

    if not html:
        # Graceful fallback: return what we can
        return {
            "job_id": job_id_or_url,
            "job_url": url,
            "title": None,
            "company": None,
            "location": None,
            "description": None,
        }

    soup = BeautifulSoup(html, "html.parser")

    # Title (robust fallbacks)
    title = None
    h1 = (
        soup.select_one("h1.jobsearch-JobInfoHeader-title")
        or soup.select_one("h1")
        or soup.select_one("h2.jobsearch-JobInfoHeader-title")
    )
    if h1:
        title = h1.get_text(strip=True)

    # Company (robust fallbacks)
    company = None
    cands = [
        ".jobsearch-CompanyInfoWithoutHeaderImage div:nth-of-type(1)",
        ".jobsearch-InlineCompanyRating div:nth-of-type(1)",
        "a[data-tn-element='companyName']",
        "div.jobsearch-CompanyInfoContainer a",
        "div.jobsearch-CompanyInfoContainer div",
    ]
    for sel in cands:
        el = soup.select_one(sel)
        if el and el.get_text(strip=True):
            company = el.get_text(strip=True)
            break

    # Location (robust fallbacks)
    location = None
    loc_cands = [
        ".jobsearch-JobInfoHeader-subtitle div:last-child",
        ".jobsearch-CompanyInfoWithoutHeaderImage + div",
        "[data-testid='inlineHeader-companyLocation']",
    ]
    for sel in loc_cands:
        el = soup.select_one(sel)
        if el and el.get_text(strip=True):
            location = el.get_text(strip=True)
            break

    # Description
    desc = None
    desc_el = soup.select_one("#jobDescriptionText") or soup.select_one("div#jobDescriptionText")
    if desc_el:
        desc = desc_el.get_text("\n", strip=True)

    # Keep a stable job_id (jk) if present in the URL
    job_id = job_id_or_url
    try:
        q = parse_qs(urlparse(url).query)
        if "jk" in q and q["jk"]:
            job_id = q["jk"][0]
    except Exception:
        pass

    return {
        "job_id": job_id,
        "job_url": url,
        "title": title,
        "company": company,
        "location": location,
        "description": desc,
    }


# ---------------------------
# Async-friendly adapter
# ---------------------------
class IndeedTools:
    """
    Adapter used by jox.mcp.tool_adapters.get_job_tools('indeed').

    Exposes async methods that wrap the synchronous implementations using
    asyncio.to_thread, so the orchestrator can always `await` them.
    """

    async def search_jobs(
        self,
        search_term: str,
        location: str,
        days: int = 7,
        limit: int = 30,
        country: Optional[str] = None,
        **_,
    ) -> List[Dict]:
        return await asyncio.to_thread(
            search_jobs,
            query=search_term,
            location=location,
            days=days,
            limit=limit,
            country=country,
        )

    async def get_job_details(self, job_id_or_url: str, country: Optional[str] = None, **_) -> Dict:
        return await asyncio.to_thread(get_job_details, job_id_or_url, country)
