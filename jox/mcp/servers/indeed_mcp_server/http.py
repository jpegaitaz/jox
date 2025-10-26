# jox/mcp/servers/indeed_mcp_server/http.py
from __future__ import annotations
import random, time, re
from typing import Optional
import requests

from .config.settings import SETTINGS, COUNTRY_TLD

_session: Optional[requests.Session] = None

def _base_headers():
    return {
        "User-Agent": SETTINGS.http.user_agent,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": SETTINGS.http.accept_language,
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
        "DNT": "1",
    }

def _get() -> requests.Session:
    global _session
    if _session is None:
        s = requests.Session()
        s.headers.update(_base_headers())
        _session = s
    return _session

def _sleep_jitter():
    lo, hi = SETTINGS.http.min_sleep_s, SETTINGS.http.max_sleep_s
    time.sleep(random.uniform(lo, hi))

_COUNTRY_TO_TLD = {
    # common
    "switzerland": "indeed.ch",
    "ch": "indeed.ch",
    "france": "indeed.fr",
    "fr": "indeed.fr",
    "germany": "indeed.de",
    "de": "indeed.de",
    "italy": "indeed.it",
    "it": "indeed.it",
    "spain": "indeed.es",
    "es": "indeed.es",
    "united kingdom": "indeed.co.uk",
    "uk": "indeed.co.uk",
    "ireland": "ie.indeed.com",
    "ie": "ie.indeed.com",
    "netherlands": "nl.indeed.com",
    "nl": "nl.indeed.com",
    "belgium": "be.indeed.com",
    "be": "be.indeed.com",
    "austria": "at.indeed.com",
    "at": "at.indeed.com",
    "portugal": "pt.indeed.com",
    "pt": "pt.indeed.com",
    # fallback
    "us": "www.indeed.com",
    "united states": "www.indeed.com",
}

def base_domain_for_country(country_or_location: Optional[str]) -> str:
    """
    Accepts 'Switzerland', 'CH', 'ch', 'Zurich, Switzerland', etc.
    Returns an Indeed domain; defaults to www.indeed.com when unknown.
    """
    if not country_or_location:
        return "www.indeed.com"
    key = country_or_location.strip().lower()
    # try exact
    if key in _COUNTRY_TO_TLD:
        return _COUNTRY_TO_TLD[key]
    # try last token (e.g., "Zurich, Switzerland")
    parts = re.split(r"[,\s]+", key)
    for token in reversed(parts):
        if token in _COUNTRY_TO_TLD:
            return _COUNTRY_TO_TLD[token]
    # last resort: mapping by known names inside the string
    for k, dom in _COUNTRY_TO_TLD.items():
        if k in key:
            return dom
    return "www.indeed.com"

def http_get(url: str, *, country: str | None = None) -> str:
    """
    Fetch HTML with realistic headers + retries.
    If 403 persists and selenium fallback enabled, try Selenium scrape.
    """
    sess = _get()
    last_exc: Exception | None = None

    for attempt in range(SETTINGS.http.retries):
        try:
            _sleep_jitter()
            r = sess.get(url, timeout=SETTINGS.http.timeout_s)
            if r.status_code == 403 and attempt < SETTINGS.http.retries - 1:
                # Try once with country domain swap if we were on .com
                if "www.indeed.com" in url and country:
                    dom = base_domain_for_country(country)
                    swapped = url.replace("www.indeed.com", dom)
                    url = swapped
                # rotate Accept-Language slightly
                sess.headers.update({"Accept-Language": SETTINGS.http.accept_language})
                continue

            r.raise_for_status()
            return r.text
        except Exception as e:
            last_exc = e

    # Optional Selenium fallback (low-volume, more resilient)
    if SETTINGS.http.use_selenium_fallback:
        try:
            return selenium_get_html(url)
        except Exception as e:
            last_exc = e

    # Give up
    raise last_exc if last_exc else RuntimeError("HTTP GET failed")

# --- Selenium fallback (simple) ---
def selenium_get_html(url: str) -> str:
    """
    Minimal, headless Selenium fallback for stubborn pages.
    Requires Chrome + chromedriver available (selenium-manager will auto-resolve).
    """
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.common.by import By

    opts = Options()
    opts.add_argument("--headless=new")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--no-sandbox")
    opts.add_argument(f"--user-agent={SETTINGS.http.user_agent}")
    driver = webdriver.Chrome(options=opts)
    try:
        driver.get(url)
        time.sleep(2.0)  # allow initial content; adjust if needed
        return driver.page_source
    finally:
        driver.quit()

JOBKEY_RE = re.compile(r"[?&]jk=([a-zA-Z0-9]+)")

def extract_jobkey(url: str) -> str | None:
    """Return Indeed job key (jk) from a URL, or None if not present."""
    m = JOBKEY_RE.search(url or "")
    return m.group(1) if m else None
