# jox/mcp/servers/jobup_mcp_server/tools.py
from __future__ import annotations
import logging, time
from typing import List, Dict, Any, Optional
from urllib.parse import urlencode

from bs4 import BeautifulSoup
from selenium.webdriver.common.by import By
from selenium.common.exceptions import NoSuchElementException
from .driver import get_simple_driver

logger = logging.getLogger(__name__)

BASE = "https://www.jobup.ch/fr/emplois/"


def _search_url(term: str, location: str) -> str:
    from urllib.parse import quote
    return f"{BASE}?term={quote(term)}&location={quote(location)}"


def _safe_text(el) -> str:
    return " ".join((el.get_text(separator=" ", strip=True) if el else "").split())


def _parse_cards(html: str) -> List[Dict[str, Any]]:
    soup = BeautifulSoup(html, "html.parser")
    out: List[Dict[str, Any]] = []

    # Prefer explicit result anchors
    for a in soup.select("a[href*='/fr/emplois/detail/']"):
        href = a.get("href") or ""
        if not href:
            continue
        title = _safe_text(a)
        card = a.find_parent("article") or a.find_parent("li") or a.find_parent("div")
        company_el = None
        for sel in [
            "[data-cy='company-name']",
            ".company-name",
            ".CompanyName",
            ".company",
            "a[data-cy='company-name']",
        ]:
            company_el = (card.select_one(sel) if card else None) or company_el
        loc_el = None
        for sel in [
            "[data-cy='job-location']",
            ".job-location",
            ".JobLocation",
            ".location",
        ]:
            loc_el = (card.select_one(sel) if card else None) or loc_el

        company = _safe_text(company_el)
        location = _safe_text(loc_el)
        jid = href.rstrip("/").split("/")[-1].split("?")[0]
        out.append({
            "id": jid or href,
            "title": title,
            "company": company if company != title else "",
            "location": location,
            "url": "https://www.jobup.ch" + href if href.startswith("/") else href,
        })

    # de-dupe by id
    seen, dedup = set(), []
    for r in out:
        k = r["id"] or r["url"]
        if k in seen:
            continue
        seen.add(k)
        dedup.append(r)
    return dedup


def search_jobs(term: str, location: str, limit: int = 30) -> List[Dict[str, Any]]:
    url = _search_url(term, location)
    logger.info("Jobup search: q='%s', l='%s', limit=%s (%s)", term, location, limit, url)

    driver = get_simple_driver()
    try:
        driver.get(url)
        time.sleep(1.0)

        # Dismiss cookie banner if present
        for sel in [
            "button#onetrust-accept-btn-handler",
            "button[aria-label*='Accepter']",
            "button[aria-label*='Accept']",
        ]:
            try:
                btns = driver.find_elements(By.CSS_SELECTOR, sel)
                if btns:
                    btns[0].click()
                    time.sleep(0.4)
                    break
            except Exception:
                pass

        results: List[Dict[str, Any]] = []
        seen = 0
        # Scroll a few times to load virtualized content
        for _ in range(12):
            driver.execute_script("window.scrollBy(0, 1200);")
            time.sleep(0.5)
            results = _parse_cards(driver.page_source)
            if len(results) >= limit:
                break
            if len(results) == seen:
                # no growth — stop
                break
            seen = len(results)

        return results[:limit]
    finally:
        try:
            driver.quit()
        except Exception:
            pass


def _try_click(driver, selectors: list[str]) -> None:
    for sel in selectors:
        try:
            el = driver.find_element(By.CSS_SELECTOR, sel)
            el.click()
            time.sleep(0.2)
            return
        except Exception:
            continue


def get_job_details(job_url_or_id: str) -> Dict[str, Any]:
    """
    Open a Jobup job page, expand 'see more' toggles, and extract a robust description.
    """
    url = job_url_or_id
    if not url.startswith("http"):
        url = f"https://www.jobup.ch/fr/emplois/detail/{job_url_or_id}/"

    driver = get_simple_driver()
    try:
        driver.get(url)
        time.sleep(0.8)

        # Expand typical "Voir plus" sections if they exist
        _try_click(driver, [
            "button[aria-expanded='false'][aria-controls*='description']",
            "button:has(span:contains('Voir plus'))",
            "button[aria-label*='Voir plus']",
            "button[aria-label*='Show more']",
        ])
        time.sleep(0.3)

        html = driver.page_source
        soup = BeautifulSoup(html, "html.parser")

        title_el = soup.select_one("h1, [data-cy='job-title']")
        company_el = soup.select_one("[data-cy='company-name'], .company, .company-name")
        location_el = soup.select_one("[data-cy='job-location'], .location, .job-location")

        # Grab all candidate description blocks and concatenate
        desc_parts = []
        for sel in [
            "[data-cy='job-description']",
            "section.job-description",
            "div[data-testid='job-description']",
            "section[data-cy='job-ad']",
            "article",
            "main",
        ]:
            for d in soup.select(sel):
                txt = _safe_text(d)
                if txt and txt not in desc_parts:
                    desc_parts.append(txt)
        description = "\n\n".join(desc_parts).strip()

        # ultra-fallback: take center column main text
        if not description:
            main = soup.find("main")
            description = _safe_text(main)

        jid = url.rstrip("/").split("/")[-2] if "/detail/" in url else url

        return {
            "job_id": jid,
            "job_url": url,
            "title": _safe_text(title_el),
            "company": _safe_text(company_el),
            "location": _safe_text(location_el),
            "description": description,
        }
    finally:
        try:
            driver.quit()
        except Exception:
            pass
