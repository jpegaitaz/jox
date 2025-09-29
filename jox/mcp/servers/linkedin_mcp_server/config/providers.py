# src/linkedin_mcp_server/config/providers.py
# SPDX-License-Identifier: Apache-2.0
"""
JOX-hardened config providers.

Principles:
- NO keyring or persistent secret storage (env-only secrets elsewhere).
- Minimal, read-only helpers for ChromeDriver path discovery.
- Keep legacy function names to avoid breaking imports, but fail closed if
  anything tries to use keyring-related APIs.
"""

from __future__ import annotations

import logging
import os
import platform
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Keyring-related API: disabled (fail closed)
# ---------------------------------------------------------------------------

SERVICE_NAME = "linkedin_mcp_server"
EMAIL_KEY = "linkedin_email"
PASSWORD_KEY = "linkedin_password"
COOKIE_KEY = "linkedin_cookie"

def _disabled(*_args, **_kwargs):
    raise RuntimeError(
        "Keyring/keychain operations are disabled in JOX. "
        "Use env-only LINKEDIN_COOKIE; secrets are never persisted."
    )

def get_keyring_name() -> str:
    # Keep the signature; return a descriptive string without touching any OS keychain.
    system = platform.system()
    if system == "Darwin":
        return "macOS Keychain (DISABLED in JOX)"
    if system == "Windows":
        return "Windows Credential Locker (DISABLED in JOX)"
    return "Keyring backend (DISABLED in JOX)"

# Disabled read/write helpers (fail fast)
get_secret_from_keyring = _disabled
set_secret_in_keyring = _disabled
get_credentials_from_keyring = _disabled
save_credentials_to_keyring = _disabled
clear_credentials_from_keyring = _disabled
get_cookie_from_keyring = _disabled
save_cookie_to_keyring = _disabled
clear_cookie_from_keyring = _disabled

def check_keychain_data_exists() -> Dict[str, bool]:
    # Return a safe, non-erroring summary implying "nothing stored".
    return {
        "has_email": False,
        "has_password": False,
        "has_cookie": False,
        "has_credentials": False,
        "has_any": False,
    }

def clear_existing_keychain_data() -> Dict[str, bool]:
    # Nothing to clear (since we never store); report success.
    return {"credentials_cleared": True, "cookie_cleared": True}

def clear_all_keychain_data() -> bool:
    # Nothing to clear; report success.
    return True

# ---------------------------------------------------------------------------
# ChromeDriver path discovery
# ---------------------------------------------------------------------------

# --- shim for vendored imports expecting `chrome_driver` ---
import os, os.path
from typing import Optional

def chrome_driver() -> Optional[str]:
    """
    Return an explicit ChromeDriver path if configured, else None.
    JOX is fine with Selenium Manager auto-detection; this is only
    to satisfy legacy imports.
    """
    path = os.getenv("CHROMEDRIVER") or os.getenv("CHROMEDRIVER_PATH")
    if path and os.path.exists(path):
        return path
    return None


def get_chromedriver_paths() -> List[str]:
    """
    Return candidate ChromeDriver paths. This does NOT verify executability;
    callers can test existence themselves.
    """
    candidates: List[str] = []

    # 1) Respect explicit env var if set
    env_path = os.getenv("CHROMEDRIVER")
    if env_path:
        candidates.append(env_path)

    # 2) Common Unix/macOS locations
    candidates.extend([
        "/usr/local/bin/chromedriver",
        "/usr/bin/chromedriver",
        "/opt/homebrew/bin/chromedriver",  # Apple Silicon Homebrew
        "/Applications/chromedriver",
    ])

    # 3) Project-relative "drivers/chromedriver"
    try:
        here = Path(__file__).resolve()
        proj_driver = here.parents[3] / "drivers" / "chromedriver"
        candidates.append(str(proj_driver))
    except Exception:
        # Be robust in odd layouts; ignore if we can't compute
        pass

    # 4) Windows locations
    if platform.system() == "Windows":
        candidates.extend([
            r"C:\Program Files\Google\Chrome\Application\chromedriver.exe",
            r"C:\Program Files\chromedriver.exe",
            r"C:\Program Files (x86)\chromedriver.exe",
        ])

    # De-duplicate while preserving order
    seen = set()
    uniq: List[str] = []
    for p in candidates:
        if p and p not in seen:
            uniq.append(p)
            seen.add(p)

    logger.debug("ChromeDriver candidate paths: %s", uniq)
    return uniq
