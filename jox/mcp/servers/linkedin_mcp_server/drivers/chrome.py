# linkedin_mcp_server/drivers/chrome.py
# SPDX-License-Identifier: Apache-2.0
"""
Hardened Chrome WebDriver management for LinkedIn scraping (JOX).

- Local Selenium only (no HTTP listeners, no remote debugging ports here).
- Env-only auth (LINKEDIN_COOKIE='li_at=...'); no keyring usage.
- Minimal, safer Chrome flags; avoid '--no-sandbox' unless explicitly allowed.
- Direct cookie login (deterministic): visit linkedin.com -> set li_at -> go to /feed -> verify.
"""

from __future__ import annotations

import logging
import os
import platform
import time
from typing import Dict, Optional

from selenium import webdriver
from selenium.common.exceptions import WebDriverException, TimeoutException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service

from ..config import get_config
from ..exceptions import DriverInitializationError

# We keep these imports for compatibility with callers that catch them.
try:
    from linkedin_scraper.exceptions import (
        CaptchaRequiredError,
        InvalidCredentialsError,
        LoginTimeoutError,
        RateLimitError,
        SecurityChallengeError,
        TwoFactorAuthError,
    )
except Exception:  # If the lib isn't present, define light stubs to avoid crashes
    class _E(RuntimeError): ...
    class CaptchaRequiredError(_E): ...
    class InvalidCredentialsError(_E): ...
    class LoginTimeoutError(_E): ...
    class RateLimitError(_E): ...
    class SecurityChallengeError(_E): ...
    class TwoFactorAuthError(_E): ...

logger = logging.getLogger(__name__)

# Global driver registry (single session for now)
active_drivers: Dict[str, webdriver.Chrome] = {}


# -------------------------
# User-Agent management
# -------------------------
def get_default_user_agent() -> str:
    """Platform-specific default UA; may be overridden by config.chrome.user_agent."""
    system = platform.system()
    # Keep a plausible modern UA; details are less important than consistency.
    if system == "Windows":
        return "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    elif system == "Darwin":
        return "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    else:
        return "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"


# -------------------------
# Chrome construction
# -------------------------
def create_chrome_options(config) -> Options:
    """
    Create hardened Chrome options for LinkedIn scraping.
    Avoid risky flags like '--no-sandbox' unless explicitly permitted.
    """
    opts = Options()

    logger.info("Running browser in %s mode", "headless" if config.chrome.headless else "visible")
    if config.chrome.headless:
        opts.add_argument("--headless=new")

    # Conservative, safer flags
    opts.add_argument("--window-size=1280,800")
    opts.add_argument("--disable-extensions")
    opts.add_argument("--disable-background-networking")
    opts.add_argument("--disable-sync")
    opts.add_argument("--no-default-browser-check")
    opts.add_argument("--disable-client-side-phishing-detection")

    # Allow explicit override for constrained containers (opt-in only)
    if os.getenv("JOX_ALLOW_NO_SANDBOX", "0") == "1":
        opts.add_argument("--no-sandbox")
    if os.getenv("JOX_ALLOW_DEV_SHM", "0") == "1":
        opts.add_argument("--disable-dev-shm-usage")

    # User agent
    ua = config.chrome.user_agent or get_default_user_agent()
    opts.add_argument(f"--user-agent={ua}")

    # Additional browser args if caller provided any (trusted only)
    for arg in getattr(config.chrome, "browser_args", []) or []:
        # We do NOT pass through remote-debugging or allow-origins flags
        if "--remote-debugging-port" in arg or "--remote-allow-origins" in arg:
            logger.warning("Dropping unsafe Chrome flag: %s", arg)
            continue
        opts.add_argument(arg)

    return opts


def create_chrome_service(config):
    """
    Create Chrome Service using explicit driver path when provided.
    """
    chromedriver_path = (
        os.environ.get("CHROMEDRIVER_PATH")
        or os.environ.get("CHROMEDRIVER")
        or config.chrome.chromedriver_path
    )

    if chromedriver_path:
        logger.info("Using ChromeDriver at path: %s", chromedriver_path)
        return Service(executable_path=chromedriver_path)
    else:
        logger.info("Using auto-detected ChromeDriver (selenium-manager)")
        return None


def _init_driver(config) -> webdriver.Chrome:
    """Internal: initialize Chrome with options + service."""
    opts = create_chrome_options(config)
    service = create_chrome_service(config)
    if service:
        driver = webdriver.Chrome(service=service, options=opts)
    else:
        driver = webdriver.Chrome(options=opts)

    # Reasonable timeouts
    driver.set_page_load_timeout(60)
    driver.implicitly_wait(5)
    return driver


def create_temporary_chrome_driver() -> webdriver.Chrome:
    """
    Create a temporary Chrome WebDriver instance for one-off operations.
    Caller MUST quit() it.
    """
    logger.info("Creating temporary Chrome WebDriver...")
    try:
        driver = _init_driver(get_config())
        logger.info("Temporary Chrome WebDriver created.")
        return driver
    except Exception as e:
        logger.error("Failed to create temporary driver: %s", e)
        raise


def create_chrome_driver() -> webdriver.Chrome:
    """
    Create a new Chrome WebDriver instance.
    """
    logger.info("Initializing Chrome WebDriver...")
    try:
        driver = _init_driver(get_config())
        logger.info("Chrome WebDriver initialized.")
        return driver
    except Exception as e:
        logger.error("Error initializing Chrome WebDriver: %s", e)
        raise


# -------------------------
# Authentication (cookie)
# -------------------------
def _extract_li_at(cookie: str) -> str:
    """
    Accepts either 'li_at=...' or raw token and returns the token value.
    """
    c = (cookie or "").strip()
    if not c:
        raise InvalidCredentialsError("Empty cookie provided")

    if c.lower().startswith("li_at="):
        token = c.split("=", 1)[1].strip()
    else:
        token = c

    if not token:
        raise InvalidCredentialsError("Malformed LinkedIn cookie (no token)")

    return token


def login_with_cookie(driver: webdriver.Chrome, cookie: str) -> bool:
    """
    Direct cookie login:
      1) open linkedin.com (sets cookie domain scope),
      2) clear any cookies,
      3) add li_at cookie,
      4) navigate to /feed/ and verify.
    """
    try:
        token = _extract_li_at(cookie)

        logger.info("Attempting cookie authentication...")
        driver.set_page_load_timeout(45)

        # Step 1: open base domain to allow adding cookies
        driver.get("https://www.linkedin.com/")

        # Step 2: clear and set cookie
        try:
            driver.delete_cookie("li_at")
        except Exception:
            pass

        driver.add_cookie({
            "name": "li_at",
            "value": token,
            "domain": ".linkedin.com",
            "path": "/",
            "secure": True,
            "httpOnly": True,
        })

        # Step 3/4: go to feed and verify
        driver.get("https://www.linkedin.com/feed/")
        time.sleep(2.0)  # brief settle

        current_url = driver.current_url or ""
        page_ok = any(ind in current_url for ind in ("/feed/", "/mynetwork/", "/messaging/"))
        if page_ok:
            logger.info("Cookie authentication successful.")
            return True

        # Fallback: try once more after a short wait
        time.sleep(1.5)
        driver.get("https://www.linkedin.com/feed/")
        current_url = driver.current_url or ""
        page_ok = any(ind in current_url for ind in ("/feed/", "/mynetwork/", "/messaging/"))
        if page_ok:
            logger.info("Cookie authentication successful (retry).")
            return True

        logger.warning("Cookie authentication uncertain; current page: %s", current_url)
        return False

    except TimeoutException:
        logger.warning("Cookie authentication failed - page load timeout (likely invalid cookie)")
        return False
    except InvalidCredentialsError as e:
        logger.error("Cookie authentication failed: %s", e)
        return False
    except Exception as e:
        logger.error("Cookie authentication encountered an error: %s", e)
        return False
    finally:
        # Restore normal timeout
        try:
            driver.set_page_load_timeout(60)
        except Exception:
            pass


def login_to_linkedin(driver: webdriver.Chrome, authentication: str) -> None:
    """
    Log in using session cookie; raise appropriate errors on failure.
    """
    if login_with_cookie(driver, authentication):
        logger.info("Successfully logged in to LinkedIn using cookie")
        return

    # If we get here, cookie authentication failed
    logger.error("Cookie authentication failed")
    # JOX: do NOT clear any stored auth (we never store secrets).
    # Attempt to identify likely cause; raise a precise error if possible.
    try:
        current_url = driver.current_url or ""
        source = (driver.page_source or "").lower()

        if "checkpoint/challenge" in current_url:
            if "security check" in source:
                raise SecurityChallengeError(
                    "LinkedIn requires a security challenge. Please complete it manually and retry."
                )
            raise CaptchaRequiredError("Captcha required by LinkedIn.")
        else:
            raise InvalidCredentialsError("Cookie authentication failed - cookie may be expired or invalid.")
    except (CaptchaRequiredError, SecurityChallengeError, InvalidCredentialsError):
        raise
    except Exception as e:
        raise LoginTimeoutError(f"Login failed: {e!s}")


# -------------------------
# Driver lifecycle helpers
# -------------------------
def get_or_create_driver(authentication: str) -> webdriver.Chrome:
    """
    Return a logged-in Chrome driver, creating one if necessary.
    """
    session_id = "default"  # Single-session design for now

    if session_id in active_drivers:
        logger.info("Using existing Chrome WebDriver session")
        return active_drivers[session_id]

    config = get_config()

    try:
        driver = create_chrome_driver()
        login_to_linkedin(driver, authentication)
        active_drivers[session_id] = driver
        logger.info("Chrome WebDriver session created and authenticated successfully")
        return driver

    except (CaptchaRequiredError, InvalidCredentialsError, SecurityChallengeError, TwoFactorAuthError, RateLimitError, LoginTimeoutError) as e:
        try:
            driver.quit()
        except Exception:
            pass
        raise e

    except WebDriverException as e:
        error_msg = f"Error creating web driver: {e}"
        logger.error(error_msg)
        try:
            driver.quit()
        except Exception:
            pass
        raise DriverInitializationError(error_msg)


def close_all_drivers() -> None:
    """Close all active drivers and clean up resources."""
    global active_drivers
    for session_id, driver in list(active_drivers.items()):
        try:
            logger.info("Closing Chrome WebDriver session: %s", session_id)
            driver.quit()
        except Exception as e:
            logger.warning("Error closing driver %s: %s", session_id, e)
        finally:
            active_drivers.pop(session_id, None)
    logger.info("All Chrome WebDriver sessions closed")


def get_active_driver() -> Optional[webdriver.Chrome]:
    """
    Get the currently active driver without creating a new one.
    """
    return active_drivers.get("default")


def capture_session_cookie(driver: webdriver.Chrome) -> Optional[str]:
    """
    Capture LinkedIn 'li_at' cookie from an authenticated session.
    """
    try:
        c = driver.get_cookie("li_at")
        if c and c.get("value"):
            return f"li_at={c['value']}"
        return None
    except Exception as e:
        logger.warning("Failed to capture session cookie: %s", e)
        return None
