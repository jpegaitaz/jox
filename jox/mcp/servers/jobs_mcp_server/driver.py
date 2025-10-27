# jox/mcp/servers/jobs_mcp_server/driver.py
from __future__ import annotations
import os
import logging
from typing import Optional
from selenium import webdriver
from selenium.webdriver.chrome.options import Options

logger = logging.getLogger(__name__)

def get_chrome_driver(headless: Optional[bool] = None) -> webdriver.Chrome:
    """
    Create a Chrome WebDriver consistent with other MCP servers (jobup).
    Uses HEADLESS by default; override with env JOBS_HEADLESS=0 for local debug.
    """
    if headless is None:
        headless = os.getenv("JOBS_HEADLESS", "1") != "0"

    # logger.info("Initializing Chrome WebDriver for jobs.ch (headless=%s)...", headless)
    opts = Options()
    if headless:
        opts.add_argument("--headless=new")
    # sensible defaults for containers/CI
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--window-size=1400,1000")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--disable-blink-features=AutomationControlled")
    driver = webdriver.Chrome(options=opts)
    # logger.info("Chrome WebDriver (jobs.ch) initialized.")
    return driver
