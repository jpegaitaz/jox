# jox/mcp/servers/linkedin_mcp_server/config/settings.py
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from typing import List, Optional

TRUTHY = {"1", "true", "yes", "on", "y", "t"}
FALSY = {"0", "false", "no", "off", "n", "f"}

def _env_bool(name: str, default: bool) -> bool:
    v = os.getenv(name)
    if v is None:
        return default
    v = v.strip().lower()
    if v in TRUTHY:
        return True
    if v in FALSY:
        return False
    return default

@dataclass
class _ChromeCfg:
    headless: bool = field(default_factory=lambda: _env_bool("HEADLESS", True))
    chromedriver_path: Optional[str] = field(default_factory=lambda: os.getenv("CHROMEDRIVER") or os.getenv("CHROMEDRIVER_PATH"))
    user_agent: Optional[str] = field(default_factory=lambda: os.getenv("USER_AGENT"))
    browser_args: List[str] = field(default_factory=list)

@dataclass
class _Settings:
    # logging
    log_level: str = field(default_factory=lambda: os.getenv("LOG_LEVEL", "INFO").upper())
    # interactive (used for messages & timeouts; safe detection)
    is_interactive: bool = field(default_factory=lambda: bool(getattr(sys.stdin, "isatty", lambda: False)()) and bool(getattr(sys.stdout, "isatty", lambda: False)()))
    # chrome sub-config expected by the driver
    chrome: _ChromeCfg = field(default_factory=_ChromeCfg)

# Singleton-ish settings object
SETTINGS = _Settings()
