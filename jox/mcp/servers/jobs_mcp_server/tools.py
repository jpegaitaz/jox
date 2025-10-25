# jox/mcp/servers/jobs_mcp_server/tools.py
from __future__ import annotations

import logging
import time
import urllib.parse
from typing import Dict, Any, List, Optional

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from .driver import get_chrome_driver

logger = logging.getLogger(__name__)


# --------- URL building ----------
def _build_search_urls(search_term: str, location: str, locale_hint: str = "en") -> List[str]:
    """
    Build a small set of candidate search URLs for jobs.ch.
    We try EN and FR paths, and both 'term' and 'keywords' query params.
    """
    term = urllib.parse.quote_plus((search_term or "").strip())
    loc = urllib.parse.quote_plus((location or "").strip())

    urls: List[str] = [
        # English
        f"https://www.jobs.ch/{locale_hint}/vacancies/?term={term}&location={loc}",
        f"https://www.jobs.ch/{locale_hint}/vacancies/?keywords={term}&location={loc}",
        f"https://www.jobs.ch/{locale_hint}/vacancies/?term={term}",
        # French (lots of Swiss postings are FR)
        f"https://www.jobs.ch/fr/offres-emplois/?term={term}&location={loc}",
        f"https://www.jobs.ch/fr/offres-emplois/?keywords={term}&location={loc}",
        f"https://www.jobs.ch/fr/offres-emplois/?term={term}",
        # EN fallback without location
        f"https://www.jobs.ch/en/vacancies/?term={term}",
    ]
    # Deduplicate while preserving order
    seen = set()
    final: List[str] = []
    for u in urls:
        if u not in seen:
            final.append(u)
            seen.add(u)
    return final


# --------- DOM helpers ----------
def _find_job_cards(driver) -> List[Any]:
    """
    Return a list of elements representing job cards (articles), or detail anchors as fallback.
    Designed to be resilient to UI tweaks.
    """
    try:
        WebDriverWait(driver, 10).until(
            EC.any_of(
                EC.presence_of_element_located((By.CSS_SELECTOR, "[data-cy='search-result-list']")),
                EC.presence_of_element_located((By.CSS_SELECTOR, "a[href*='/offres-emplois/detail/'], a[href*='/vacancies/detail/']")),
            )
        )
    except Exception:
        # We'll try to find anchors below regardless
        pass

    # Preferred: list container with articles
    cards = driver.find_elements(By.CSS_SELECTOR, "[data-cy='search-result-list'] article")
    if cards:
        return cards

    # Fallback: collect the anchors themselves; the card extractor handles both
    anchors = driver.find_elements(By.CSS_SELECTOR, "a[href*='/offres-emplois/detail/'], a[href*='/vacancies/detail/']")
    return anchors


def _card_to_listing(el) -> Optional[Dict[str, Any]]:
    """
    Extract a uniform listing dict from a card element or a detail <a> fallback.
    Expected keys: title, company, job_url, location, snippet
    """
    try:
        # If we already have a link (fallback mode), use it.
        a = el
        if el.tag_name.lower() != "a":
            a = el.find_element(By.CSS_SELECTOR, "a[href*='/offres-emplois/detail/'], a[href*='/vacancies/detail/']")

        job_url = (a.get_attribute("href") or "").strip()
        if not job_url:
            return None

        # Title from anchor text or heading inside the card
        title = (a.text or "").strip()
        if not title:
            try:
                title = el.find_element(By.CSS_SELECTOR, "h2, h3").text.strip()
            except Exception:
                pass
        if not title:
            # Last resort: first non-empty line
            txt = (el.text or "").strip()
            title = (txt.split("\n", 1)[0] if txt else "").strip() or "Role"

        # Company (best-effort)
        company = ""
        for sel in ("[data-cy='company-name']", "a[href*='/company/']", ".company", "ul li"):
            try:
                t = el.find_element(By.CSS_SELECTOR, sel).text.strip()
                if t and len(t) < 120:
                    company = t
                    break
            except Exception:
                continue

        # Location (best-effort)
        location = ""
        for sel in ("[data-cy='job-location']", "[data-cy='city']", ".location", "li[data-cy='job-location']", "ul li"):
            try:
                t = el.find_element(By.CSS_SELECTOR, sel).text.strip()
                if t:
                    location = t
                    break
            except Exception:
                continue

        # Snippet/teaser
        snippet = ""
        for sel in ("[data-cy='snippet']", "[data-cy='teaser']", "p"):
            try:
                t = el.find_element(By.CSS_SELECTOR, sel).text.strip()
                if t and len(t) > 30:
                    snippet = t
                    break
            except Exception:
                continue

        return {
            "title": title,
            "company": company,
            "job_url": job_url,
            "location": location,
            "snippet": snippet,
        }
    except Exception:
        return None


# --------- Public MCP-style tools ----------
def search_jobs(
    *,
    search_term: str,
    location: str,
    days: int = 7,      # not used by jobs.ch; kept for API symmetry
    limit: int = 30,
    country: str = "",  # not used; symmetry with other adapters
) -> List[Dict[str, Any]]:
    """
    Search jobs.ch and return a list of uniform listing dicts.
    """
    urls = _build_search_urls(search_term, location)
    driver = get_chrome_driver(headless=True)
    listings: List[Dict[str, Any]] = []
    seen_urls: set[str] = set()

    try:
        for url in urls:
            if len(listings) >= limit:
                break

            logger.info("jobs.ch search: %s", url)
            driver.get(url)

            cards = _find_job_cards(driver)
            if not cards:
                continue

            for c in cards:
                if len(listings) >= limit:
                    break
                row = _card_to_listing(c)
                if not row:
                    continue
                href = row.get("job_url")
                if not href or href in seen_urls:
                    continue
                seen_urls.add(href)
                listings.append(row)

            # If we managed to collect any from this URL, stop trying others
            if listings:
                break

        logger.info("jobs.ch search returned %d listings", len(listings))
        return listings[:limit]
    finally:
        try:
            driver.quit()
        except Exception:
            pass


def get_job_details(job_id_or_url: str) -> Dict[str, Any]:
    """
    Open a job detail page and extract title, company, location and full description.
    Accepts either a full URL or a numeric-like id (we'll format an EN path).
    """
    driver = get_chrome_driver(headless=True)
    try:
        url = job_id_or_url
        if not url.startswith("http"):
            # default to EN detail path when only an id is provided
            url = f"https://www.jobs.ch/en/vacancies/detail/{job_id_or_url}/"

        logger.info("jobs.ch details: %s", url)
        driver.get(url)

        # Try to close cookie banner if it blocks content
        try:
            WebDriverWait(driver, 3).until(
                EC.element_to_be_clickable(
                    (By.CSS_SELECTOR, "button[aria-label*='Accept'], button[aria-label*='Accepter']")
                )
            ).click()
        except Exception:
            pass

        # Wait for main content presence
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "main"))
        )
        time.sleep(0.3)  # small settle

        def _txt(by, sel) -> str:
            try:
                return driver.find_element(by, sel).text.strip()
            except Exception:
                return ""

        # Title
        title = ""
        for sel in ("h1", "[data-cy='job-title']", "header h1"):
            title = _txt(By.CSS_SELECTOR, sel)
            if title:
                break

        # Company
        company = ""
        for sel in ("[data-cy='company-name'] a", "[data-cy='company-name']", "a[href*='/company/']", "header a"):
            company = _txt(By.CSS_SELECTOR, sel)
            if company:
                break

        # Location
        location = ""
        for sel in ("[data-cy='job-location']", "[data-cy='city']", "li[data-cy='job-location']", "header li"):
            location = _txt(By.CSS_SELECTOR, sel)
            if location:
                break

        # Description — pick a substantial content block
        description = ""
        for sel in ("[data-cy='job-description']", "article", "main section", "main"):
            t = _txt(By.CSS_SELECTOR, sel)
            # avoid picking the whole page chrome; keep a reasonable lower bound
            if t and len(t) > 200:
                description = t
                break

        return {
            "title": title or "",
            "company": company or "",
            "location": location or "",
            "description": description or "",
            "job_url": url,
            "job_id": job_id_or_url,
        }
    finally:
        try:
            driver.quit()
        except Exception:
            pass
