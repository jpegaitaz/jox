# jox/mcp/servers/jobup_mcp_server/tools.py
from __future__ import annotations

import asyncio
import logging
import time
from typing import List, Dict, Any
from urllib.parse import quote, urljoin

from bs4 import BeautifulSoup
from selenium.webdriver.common.by import By

from .driver import get_simple_driver

logger = logging.getLogger(__name__)

BASE = "https://www.jobup.ch/fr/emplois/"


def _search_url(term: str, location: str) -> str:
    return f"{BASE}?term={quote(term)}&location={quote(location)}"


def _safe_text(el) -> str:
    return " ".join((el.get_text(separator=" ", strip=True) if el else "").split())


def _parse_cards(html: str) -> List[Dict[str, Any]]:
    soup = BeautifulSoup(html, "html.parser")
    out: List[Dict[str, Any]] = []

    # Each card links to /fr/emplois/detail/<id>/
    for a in soup.select("a[href*='/fr/emplois/detail/']"):
        href = a.get("href") or ""
        if not href:
            continue

        title = _safe_text(a)
        card = a.find_parent("article") or a.find_parent("li") or a.find_parent("div")

        company_el = None
        for sel in (
            "[data-cy='company-name']",
            "a[data-cy='company-name']",
            ".company-name",
            ".CompanyName",
            ".company",
        ):
            company_el = (card.select_one(sel) if card else None) or company_el

        loc_el = None
        for sel in (
            "[data-cy='job-location']",
            ".job-location",
            ".JobLocation",
            ".location",
        ):
            loc_el = (card.select_one(sel) if card else None) or loc_el

        company = _safe_text(company_el)
        location = _safe_text(loc_el)
        jid = href.rstrip("/").split("/")[-1].split("?")[0]

        out.append(
            {
                "id": jid or href,
                "title": title,
                "company": company if company != title else "",
                "location": location,
                "url": urljoin("https://www.jobup.ch", href) if href.startswith("/") else href,
            }
        )

    # De-dupe by id/url
    seen, dedup = set(), []
    for r in out:
        k = r["id"] or r["url"]
        if k in seen:
            continue
        seen.add(k)
        dedup.append(r)
    return dedup


def _try_click_css(driver, selectors: list[str]) -> bool:
    for sel in selectors:
        try:
            el = driver.find_element(By.CSS_SELECTOR, sel)
            el.click()
            time.sleep(0.2)
            return True
        except Exception:
            continue
    return False


def _try_click_xpath(driver, xpaths: list[str]) -> bool:
    for xp in xpaths:
        try:
            el = driver.find_element(By.XPATH, xp)
            el.click()
            time.sleep(0.2)
            return True
        except Exception:
            continue
    return False


def _search_jobs_sync(term: str, location: str, limit: int = 30) -> List[Dict[str, Any]]:
    url = _search_url(term, location)
    logger.info("Jobup search: q='%s', l='%s', limit=%s (%s)", term, location, limit, url)

    driver = get_simple_driver()
    driver.get(url)
    time.sleep(1.0)

    # Accept cookies (best-effort)
    _try_click_css(
        driver,
        [
            "#didomi-notice-agree-button",
            "button[data-cy='accept-all']",
            "button#onetrust-accept-btn-handler",
            "button[aria-label*='Accepter']",
            "button[aria-label*='Accept']",
        ],
    )

    results: List[Dict[str, Any]] = []
    seen = 0

    # Scroll to load more virtualized rows
    for _ in range(12):
        driver.execute_script("window.scrollBy(0, 1200);")
        time.sleep(0.5)
        results = _parse_cards(driver.page_source)
        if len(results) >= limit:
            break
        if len(results) == seen:
            break
        seen = len(results)

    return results[:limit]


async def search_jobs(term: str, location: str, limit: int = 30) -> List[Dict[str, Any]]:
    """Async wrapper for the blocking Selenium search."""
    return await asyncio.to_thread(_search_jobs_sync, term, location, limit)


def _get_job_details_sync(job_url_or_id: str) -> Dict[str, Any]:
    if job_url_or_id.startswith("http"):
        url = job_url_or_id
    else:
        url = f"https://www.jobup.ch/fr/emplois/detail/{job_url_or_id}/"

    driver = get_simple_driver()
    logger.info("Jobup details: %s", url)

    driver.get(url)
    time.sleep(0.8)

    # Cookie notice (ignore failures)
    _try_click_css(driver, ["#didomi-notice-agree-button", "button[data-cy='accept-all']"])

    # Expand description areas if present
    _try_click_css(
        driver,
        [
            "button[data-cy='vacancy-description__show-more']",
            "button[aria-expanded='false'][aria-controls*='description']",
            "button[aria-label*='Voir plus']",
            "button[aria-label*='Show more']",
        ],
    )
    _try_click_xpath(
        driver,
        [
            "//button[contains(., 'Voir plus')]",
            "//button[contains(., 'Afficher plus')]",
            "//button[contains(., 'Show more')]",
        ],
    )
    time.sleep(0.3)

    html = driver.page_source
    soup = BeautifulSoup(html, "html.parser")

    # Title / company / location — multiple fallbacks
    title_el = soup.select_one("[data-cy='vacancy-title'], h1[data-cy='job-title'], h1.textStyle_h3, h1")
    company_el = soup.select_one(
        "[data-cy='vacancy-company'], [data-cy='company-name'], .company, .company-name, a[data-cy='company-link']"
    )
    location_el = soup.select_one("[data-cy='vacancy-location'], [data-cy='job-location'], .location, .job-location")

    # Full description
    desc_el = soup.select_one("div[data-cy='vacancy-description']")
    description = _safe_text(desc_el)

    if not description:
        for sel in (
            "section[data-cy='job-description']",
            "section.job-description",
            "div[data-testid='job-description']",
            "section[data-cy='job-ad']",
            "article.vacancy-description",
            "div.area_description",
            "main",
        ):
            cand = soup.select_one(sel)
            description = _safe_text(cand)
            if description:
                break

    # Derive job id from URL
    cur_url = driver.current_url or url
    parts = [p for p in cur_url.rstrip("/").split("/") if p]
    job_id = None
    for part in reversed(parts):
        if part.isdigit():
            job_id = part
            break
    job_id = job_id or cur_url

    return {
        "job_id": job_id,
        "job_url": cur_url,
        "title": _safe_text(title_el),
        "company": _safe_text(company_el),
        "location": _safe_text(location_el),
        "description": description,
    }


async def get_job_details(job_url_or_id: str) -> Dict[str, Any]:
    """Async wrapper for the blocking Selenium detail fetch."""
    return await asyncio.to_thread(_get_job_details_sync, job_url_or_id)


# Adapter for jox.mcp.tool_adapters.get_job_tools('jobup')
class JobupTools:
    async def search_jobs(
        self,
        search_term: str = "",
        location: str = "",
        days: int = 7,
        limit: int = 30,
        country: str = "",
        **kwargs,
    ):
        """
        Accepts both (search_term, location) and (term, location) to be resilient to callers.
        """
        term = search_term or kwargs.get("term", "")
        return await search_jobs(term, location, limit=limit)

    async def get_job_details(self, url_or_id: str, **_):
        return await get_job_details(url_or_id)
