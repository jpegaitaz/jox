# SPDX-License-Identifier: Apache-2.0
"""
JOX-hardened configuration loader for the vendored LinkedIn MCP server.

Principles:
- ENV-ONLY secrets (LINKEDIN_COOKIE='li_at=...').
- STDIO-ONLY transport (no HTTP listeners, no host/port/path).
- NO keyring usage or credential flows (no email/password, no --get-cookie).
- Minimal, deterministic config: environment > defaults.
"""

from __future__ import annotations
import logging
import os
import sys
from typing import Optional, Dict, Any

from .schema import AppConfig  # expects nested: .linkedin, .chrome, .server

logger = logging.getLogger(__name__)

TRUTHY_VALUES = {"1", "true", "True", "yes", "Yes", "on", "ON"}
FALSY_VALUES = {"0", "false", "False", "no", "No", "off", "OFF"}

# --- Environment keys (JOX) ---
class EnvironmentKeys:
    LINKEDIN_COOKIE = "LINKEDIN_COOKIE"     # required: 'li_at=...'
    CHROMEDRIVER = "CHROMEDRIVER"           # optional: explicit path
    HEADLESS = "JOX_HEADLESS"               # "1" default
    USER_AGENT = "JOX_USER_AGENT"           # optional UA override
    LOG_LEVEL = "JOX_LOG_LEVEL"             # DEBUG|INFO|WARNING|ERROR

# --- Minimal helpers ---
def _is_tty() -> bool:
    try:
        return bool(sys.stdin and sys.stdin.isatty()) and bool(sys.stdout and sys.stdout.isatty())
    except Exception:
        return False

def _find_chromedriver() -> Optional[str]:
    """
    Minimal finder:
    1) CHROMEDRIVER env
    2) A few common locations
    """
    env_path = os.getenv(EnvironmentKeys.CHROMEDRIVER)
    if env_path and os.path.exists(env_path):
        return env_path

    candidates = [
        "/usr/local/bin/chromedriver",
        "/usr/bin/chromedriver",
        "C:\\Program Files\\Google\\Chrome\\Application\\chromedriver.exe",
        "C:\\Program Files (x86)\\Google\\Chrome\\Application\\chromedriver.exe",
    ]
    for p in candidates:
        if os.path.exists(p):
            return p
    return None

# --- Public API ---
def detect_environment() -> Dict[str, Any]:
    """
    Side-effect-free detection used to enrich defaults.
    """
    return {
        "chromedriver_path": _find_chromedriver(),
        "is_interactive": _is_tty(),
    }

def _apply_env(config: AppConfig) -> AppConfig:
    """
    Apply environment variables to config. Strict and minimal.
    """
    # LinkedIn cookie (env-only secret)
    cookie = os.environ.get(EnvironmentKeys.LINKEDIN_COOKIE, "").strip()
    if cookie:
        config.linkedin.cookie = cookie

    # Chrome
    chromedriver = os.environ.get(EnvironmentKeys.CHROMEDRIVER, "").strip()
    if chromedriver:
        config.chrome.chromedriver_path = chromedriver

    user_agent = os.environ.get(EnvironmentKeys.USER_AGENT, "").strip()
    if user_agent:
        config.chrome.user_agent = user_agent

    # Headless
    headless_val = os.environ.get(EnvironmentKeys.HEADLESS, "1")
    config.chrome.headless = headless_val in TRUTHY_VALUES

    # Log level
    log_level = os.environ.get(EnvironmentKeys.LOG_LEVEL, "INFO").upper()
    if log_level not in {"DEBUG", "INFO", "WARNING", "ERROR"}:
        log_level = "INFO"
    config.server.log_level = log_level

    # Transport is *forced* to stdio in JOX
    config.server.transport = "stdio"
    config.server.transport_explicitly_set = True

    # JOX never uses lazy get-cookie/init dance; keep deterministic
    # If your schema has lazy_init, set to False explicitly.
    if hasattr(config.server, "lazy_init"):
        config.server.lazy_init = False

    # Clear HTTP server fields if present in schema
    for attr, default_val in [("host", None), ("port", None), ("path", None)]:
        if hasattr(config.server, attr):
            setattr(config.server, attr, default_val)

    return config

def load_config() -> AppConfig:
    """
    Build an AppConfig from defaults + minimal environment.
    Precedence: environment > detection > defaults.
    No CLI parsing, no keyring, no HTTP transport.
    """
    config = AppConfig()

    # Environment/detection
    env = detect_environment()
    config.is_interactive = bool(env.get("is_interactive", False))
    detected_driver = env.get("chromedriver_path")
    if detected_driver and not getattr(config.chrome, "chromedriver_path", None):
        config.chrome.chromedriver_path = detected_driver
        logger.debug(f"Detected ChromeDriver at: {detected_driver}")

    # Env overrides
    config = _apply_env(config)

    # Validate required secret
    if not (getattr(config.linkedin, "cookie", "") or "").lower().startswith("li_at="):
        # We fail closed here. The orchestrator should set LINKEDIN_COOKIE.
        raise RuntimeError(
            "Missing or invalid LINKEDIN_COOKIE. Expected format: li_at=YOUR_COOKIE"
        )

    logger.debug("Configuration loaded (JOX-hardened): stdio-only, env-only secrets")
    return config
