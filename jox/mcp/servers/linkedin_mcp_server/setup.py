# linkedin_mcp_server/setup.py
# SPDX-License-Identifier: Apache-2.0
"""
JOX-hardened setup utilities (non-interactive).

This module intentionally excludes:
- Interactive credential prompts
- Keyring/credential storage
- Email/password login and cookie extraction

Provided helpers:
- temporary_chrome_driver(): for short-lived driver usage in diagnostics/tests
- test_cookie_validity(cookie): quick check that a given li_at works
- ensure_env_cookie(validate: bool = False): fetch LINKEDIN_COOKIE from env and
  optionally validate it via a headless login round-trip
"""

from __future__ import annotations

import logging
import os
from contextlib import contextmanager
from typing import Iterator

from selenium import webdriver

from .config.messages import ErrorMessages, InfoMessages
from .config.schema import AppConfig  # kept for type hints if needed
from .drivers.chrome import (
    create_temporary_chrome_driver,
    login_with_cookie,
)

logger = logging.getLogger(__name__)


@contextmanager
def temporary_chrome_driver() -> Iterator[webdriver.Chrome]:
    """
    Context manager for creating a temporary Chrome driver with automatic cleanup.
    """
    driver = None
    try:
        driver = create_temporary_chrome_driver()
        yield driver
    finally:
        try:
            if driver:
                driver.quit()
        except Exception as e:
            logger.warning("Error during driver cleanup: %s", e)


def test_cookie_validity(cookie: str) -> bool:
    """
    Validate a LinkedIn session cookie by attempting a cookie-based login.

    Args:
        cookie: Either 'li_at=...' or the raw token.

    Returns:
        True if LinkedIn accepts the cookie (navigates to an authenticated page), else False.
    """
    try:
        with temporary_chrome_driver() as driver:
            return bool(login_with_cookie(driver, cookie))
    except Exception as e:
        logger.warning("Cookie validation failed: %s", e)
        return False


def ensure_env_cookie(validate: bool = False) -> str:
    """
    Fetch LINKEDIN_COOKIE from the environment and (optionally) validate it.

    Args:
        validate: If True, perform a quick login check using a temporary driver.

    Returns:
        The cookie string in 'li_at=...' format.

    Raises:
        RuntimeError: If the cookie is missing, malformed, or fails validation.
    """
    raw = (os.getenv("LINKEDIN_COOKIE") or "").strip()
    if not raw:
        raise RuntimeError(ErrorMessages.no_cookie_found(is_interactive=False))

    # Normalize: accept raw token or 'li_at=...'
    cookie = raw if raw.lower().startswith("li_at=") else f"li_at={raw}"

    if not cookie.lower().startswith("li_at=") or len(cookie) <= len("li_at="):
        raise RuntimeError(ErrorMessages.invalid_cookie_format(raw))

    logger.info(InfoMessages.using_cookie_from_environment())
    logger.debug(InfoMessages.cookie_masked_preview(cookie))

    if validate:
        ok = test_cookie_validity(cookie)
        if not ok:
            raise RuntimeError("Provided LINKEDIN_COOKIE appears invalid or expired.")
    return cookie
