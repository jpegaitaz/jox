# src/linkedin_mcp_server/cli.py
# SPDX-License-Identifier: Apache-2.0
"""
CLI utilities for LinkedIn MCP server configuration (JOX-hardened).

- Generates a stdio-only MCP client config snippet.
- Never prints secrets (e.g., LINKEDIN_COOKIE).
- No keyring, no interactive prompts, no uv dependency.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, List

from .config import get_config

logger = logging.getLogger(__name__)


def _masked(val: str, prefix: int = 6) -> str:
    if not val:
        return ""
    return val[:prefix] + "***"


def print_claude_config() -> None:
    """
    Print a stdio-only Claude Desktop MCP configuration snippet.

    Notes:
    - We DO NOT include LINKEDIN_COOKIE in the printed config (avoid leaking secrets).
    - Set LINKEDIN_COOKIE in your OS environment (e.g., shell profile) instead.
    - Command uses the current Python to run jox-vendored server: `-m linkedin_mcp_server.cli_main`.
    """
    config = get_config()
    project_root = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))

    # Command & args: stdio-only entrypoint
    command = os.environ.get("PYTHON", os.sys.executable or "python")
    args: List[str] = [
        "-m",
        "linkedin_mcp_server.cli_main",
    ]

    # Safe environment variables to embed (non-sensitive)
    env_vars: Dict[str, str] = {}

    # Optional: ChromeDriver path (harmless to include)
    if config.chrome.chromedriver_path:
        env_vars["CHROMEDRIVER"] = config.chrome.chromedriver_path

    # Logging prefs (harmless)
    env_vars["JOX_LOG_LEVEL"] = config.server.log_level
    env_vars["JOX_HEADLESS"] = "1" if config.chrome.headless else "0"
    # set JOX_LOG_JSON=1 if you want JSON logs in Claude's console
    if os.getenv("JOX_LOG_JSON") in ("1", "true", "True"):
        env_vars["JOX_LOG_JSON"] = "1"

    # IMPORTANT: we never include LINKEDIN_COOKIE here.
    # Show a masked preview only (if present) so the user knows it's detected.
    cookie = os.getenv("LINKEDIN_COOKIE", "")
    if cookie:
        logger.info("LINKEDIN_COOKIE detected (masked preview: %s)", _masked(cookie))

    config_json: Dict[str, Any] = {
        "mcpServers": {
            "linkedin-scraper": {
                "command": command,
                "args": args,
                "cwd": project_root,
                "disabled": False,
                "requiredTools": [
                    "get_person_profile",
                    "get_company_profile",
                    "get_job_details",
                    "search_jobs",
                    "get_recommended_jobs",
                    "close_session",
                    "ping",
                ],
                # env section will be added below if non-empty
            }
        }
    }

    if env_vars:
        config_json["mcpServers"]["linkedin-scraper"]["env"] = env_vars

    # Render pretty JSON
    config_str = json.dumps(config_json, indent=2)

    print("\n📋 Add this to Claude Desktop (Settings → Developer → Edit Config):\n")
    print(config_str)
    print(
        "\n⚠️  Remember to set LINKEDIN_COOKIE in your OS environment, e.g.:\n"
        "   export LINKEDIN_COOKIE='li_at=YOUR_SESSION_TOKEN'\n"
        "   # (Do NOT paste your cookie into the Claude config file.)\n"
    )

    # Optional clipboard copy (no hard dependency)
    try:
        import pyperclip  # type: ignore

        pyperclip.copy(config_str)
        print("✅ Configuration copied to clipboard.")
    except Exception:
        print("ℹ️  Install 'pyperclip' to enable auto-copy (optional).")
