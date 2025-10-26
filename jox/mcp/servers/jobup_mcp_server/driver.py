# jox/mcp/servers/jobup_mcp_server/driver.py
from __future__ import annotations

import os
import logging
from typing import Optional

from selenium import webdriver
from selenium.webdriver.chrome.options import Options

logger = logging.getLogger(__name__)

# Simple module-level cache so we reuse a single browser instance
_driver_cache: Optional[webdriver.Chrome] = None


def get_simple_driver(headless: Optional[bool] = None) -> webdriver.Chrome:
    """
    Return a cached Chrome WebDriver configured for scraping Jobup.

    Args:
        headless: Force headless on/off. If None, read JOBUP_HEADLESS env
                  (default: "1" -> headless True).
    """
    global _driver_cache
    if _driver_cache is not None:
        return _driver_cache

    if headless is None:
        headless = os.getenv("JOBUP_HEADLESS", "1") != "0"

    opts = Options()
    if headless:
        # Modern selenium: add_argument("--headless=new") also works; plain --headless is fine
        opts.add_argument("--headless=new")

    # Sensible defaults for CI/containers
    opts.add_argument("--disable-gpu")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")

    # Reasonable viewport & language (Jobup is often FR in CH)
    opts.add_argument("--window-size=1366,768")
    opts.add_argument("--lang=fr-CH")

    # Keep default page load strategy; can be tuned if needed
    # opts.page_load_strategy = "normal"

    # You can add a UA if you get blocked:
    # opts.add_argument("user-agent=Mozilla/5.0 ...")

    logger.info("Initializing Chrome WebDriver for Jobup (headless=%s)...", headless)
    driver = webdriver.Chrome(options=opts)
    logger.info("Chrome WebDriver (Jobup) initialized.")

    # Optional timeouts (tweak if needed)
    driver.set_page_load_timeout(45)  # seconds
    driver.implicitly_wait(5)         # seconds

    _driver_cache = driver
    return driver


def close_driver() -> None:
    """Close and clear the cached driver."""
    global _driver_cache
    try:
        if _driver_cache:
            _driver_cache.quit()
            logger.info("Chrome WebDriver (Jobup) closed.")
    except Exception as e:
        logger.warning("Error while closing Jobup WebDriver: %s", e)
    finally:
        _driver_cache = None
