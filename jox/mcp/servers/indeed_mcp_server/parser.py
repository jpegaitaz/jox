# jox/mcp/servers/indeed_mcp_server/parser.py
from __future__ import annotations
from typing import List, Dict
from bs4 import BeautifulSoup
from urllib.parse import urljoin

def _text(el):
    return " ".join((el.get_text(separator=" ", strip=True) if el else "").split())

def parse_search_list(html: str, base_url: str = "https://www.indeed.com") -> List[Dict]:
    """
    Extract a list of jobs from an Indeed search HTML page.
    Tries multiple selector strategies and link patterns:
      - <a data-jk="...">
      - href*="viewjob?jk="
      - new Mosaic card containers
    Returns: [{title, company, location, posted, url, id}]
    """
    soup = BeautifulSoup(html, "html.parser")
    results: List[Dict] = []

    def add_job(href: str, title_el, company_el, location_el, posted_el):
        href = href or ""
        if not href:
            return
        # Normalize to absolute URL
        url = urljoin(base_url, href)
        # Job key extraction (common patterns)
        jk = None
        # try data-jk on ancestor/anchor
        a = title_el if title_el and title_el.name == "a" else title_el.find("a") if title_el else None
        if a and a.has_attr("data-jk"):
            jk = a["data-jk"]
        # fallbacks: viewjob?jk=... or &jk=...
        if not jk and "jk=" in url:
            # pull last jk= segment
            try:
                from urllib.parse import parse_qs, urlparse
                qs = parse_qs(urlparse(url).query)
                if "jk" in qs and qs["jk"]:
                    jk = qs["jk"][0]
            except Exception:
                pass

        title = _text(title_el) if title_el else ""
        company = _text(company_el) if company_el else ""
        location = _text(location_el) if location_el else ""
        posted = _text(posted_el) if posted_el else ""

        results.append({
            "id": jk or url,
            "title": title,
            "company": company,
            "location": location,
            "posted": posted,
            "url": url,
        })

    # Strategy A: Newer Mosaic cards
    for card in soup.select("div.job_seen_beacon, div.mosaic-provider-jobcards a.tapItem"):
        a = card if card.name == "a" else card.select_one("a.tapItem, a[data-jk], a[href*='viewjob?jk=']")
        if not a:
            continue
        href = a.get("href") or ""
        title_el = a.select_one("[aria-label]") or a.select_one("h2, h3, span[title]")
        company_el = card.select_one("span.companyName, div.companyName, a.companyName")
        location_el = card.select_one("div.companyLocation, span.companyLocation")
        posted_el = card.select_one("span.date, span.posted, span.result-footer")
        add_job(href, title_el, company_el, location_el, posted_el)

    # Strategy B: Classic list items
    if not results:
        for a in soup.select("a[data-jk], a[href*='viewjob?jk=']"):
            card = a.find_parent("div", class_="job_seen_beacon") or a.find_parent("td") or a.parent
            href = a.get("href") or ""
            title_el = a
            company_el = card.select_one("span.companyName, div.companyName, a.companyName") if card else None
            location_el = card.select_one("div.companyLocation, span.companyLocation") if card else None
            posted_el = card.select_one("span.date, span.posted, span.result-footer") if card else None
            add_job(href, title_el, company_el, location_el, posted_el)

    # Deduplicate by id/url
    seen = set()
    deduped = []
    for r in results:
        k = r["id"]
        if k in seen:
            continue
        seen.add(k)
        deduped.append(r)

    return deduped
