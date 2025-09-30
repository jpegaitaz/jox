# jox/mcp/servers/indeed_mcp_server/tools.py
from __future__ import annotations
import logging, urllib.parse
from typing import List, Dict, Optional

from .config.settings import SETTINGS
from .http import http_get, base_domain_for_country
from .parser import parse_search_list

logger = logging.getLogger(__name__)

def _search_url(query: str, location: str, days: int, start: int, domain: str) -> str:
    params = {
        "q": query,
        "l": location,
        "fromage": str(days),   # posted within N days
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
        html = http_get(url, country=domain)  # keeps headers/locale in sync
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

    # Pass 1: inferred domain, given 'days'
    results = _one_pass(query, location, days, limit, domain_pref)
    if results:
        return results

    # Pass 2: inferred domain, widen days
    for d in (14, 30):
        logger.info("No hits; widening window to %s days on %s", d, domain_pref)
        results = _one_pass(query, location, d, limit, domain_pref)
        if results:
            return results

    # Pass 3: fallback to .com
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

# --- add below existing imports in tools.py ---
from bs4 import BeautifulSoup

def _normalize_job_url(job_id_or_url: str, country: str | None) -> str:
    # if full URL, return as-is
    if job_id_or_url.startswith("http"):
        return job_id_or_url
    # if it looks like a jobkey, build a view URL
    dom = base_domain_for_country(country)
    return f"https://{dom}/viewjob?jk={job_id_or_url}"

def get_job_details(job_id_or_url: str, country: str | None = None) -> Dict:
    """
    Fetch a single job page and extract basic details.
    Works even if we only have a jobkey (jk) by building the view URL.
    """
    url = _normalize_job_url(job_id_or_url, country)
    html = http_get(url, country=country)
    if not html:
        # graceful fallback: at least return identifiers we know
        return {
            "job_id": job_id_or_url,
            "job_url": url,
            "title": None,
            "company": None,
            "location": None,
            "description": None,
        }

    soup = BeautifulSoup(html, "html.parser")

    # Title
    title = None
    h1 = soup.select_one("h1.jobsearch-JobInfoHeader-title") \
         or soup.select_one("h1") \
         or soup.select_one("h2.jobsearch-JobInfoHeader-title")
    if h1:
        title = h1.get_text(strip=True)

    # Company
    company = None
    cands = [
        ".jobsearch-CompanyInfoWithoutHeaderImage div:nth-of-type(1)",
        ".jobsearch-InlineCompanyRating div:nth-of-type(1)",
        "a[data-tn-element='companyName']",
        "div.jobsearch-CompanyInfoContainer a",
        "div.jobsearch-CompanyInfoContainer div"
    ]
    for sel in cands:
        el = soup.select_one(sel)
        if el and el.get_text(strip=True):
            company = el.get_text(strip=True)
            break

    # Location
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

    # Try to keep a stable job_id (jk) if present in URL
    from urllib.parse import urlparse, parse_qs
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