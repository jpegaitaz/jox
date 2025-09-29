# SPDX-License-Identifier: Apache-2.0
"""
JOX-hardened configuration entrypoint for the vendored LinkedIn MCP server code.

Goals:
- No secret persistence (no keyring/keychain; env-only cookie).
- No HTTP transport toggles here; stdio/local usage only.
- Provide a small, explicit surface: SETTINGS, Secrets, chrome_driver().
- Fail closed if legacy code tries to use keyring helpers.
"""

from __future__ import annotations
import logging
from typing import Final

from .settings import SETTINGS  # read-only runtime flags
from .secrets import Secrets     # env-only cookie accessor
from .providers import chrome_driver
from .logging_config import configure_logger

# Configure a PII-safe logger once for this package
_logger: Final = configure_logger(level=SETTINGS.log_level)
logger = logging.getLogger(__name__)

# Backwards-compat shim -------------------------------------------------------
# If any vendored modules still import keyring helpers, we raise immediately.
def _disabled(*_args, **_kwargs):
    raise RuntimeError(
        "Keyring/keychain operations are disabled in JOX. "
        "Use env-only secrets via LINKEDIN_COOKIE."
    )

# Expose names some code might expect, but make them safe no-ops that fail closed.
get_credentials_from_keyring = _disabled
save_credentials_to_keyring = _disabled
clear_credentials_from_keyring = _disabled
clear_all_keychain_data = _disabled
check_keychain_data_exists = _disabled
get_keyring_name = _disabled

# Minimal config accessor -----------------------------------------------------
# For compatibility with code that expects get_config()/reset_config(),
# return a simple object exposing our SETTINGS. No dynamic loaders.
_config = SETTINGS

def get_config():
    """Return immutable JOX SETTINGS (read-only)."""
    logger.debug("get_config called; returning immutable SETTINGS")
    return _config

def reset_config() -> None:
    """No-op in JOX (config is env-driven and immutable at runtime)."""
    logger.debug("reset_config called; JOX uses env-only immutable settings")

# Public API
__all__ = [
    "SETTINGS",
    "Secrets",
    "chrome_driver",
    "get_config",
    "reset_config",
    # disabled legacy exports (fail closed if called)
    "get_credentials_from_keyring",
    "save_credentials_to_keyring",
    "clear_credentials_from_keyring",
    "clear_all_keychain_data",
    "check_keychain_data_exists",
    "get_keyring_name",
]
