# src/linkedin_mcp_server/server.py
# SPDX-License-Identifier: Apache-2.0
"""
FastMCP server for LinkedIn tools (JOX-hardened).

- Registers all LinkedIn tools (person/company/job) in one place.
- Provides 'ping' and 'close_session' utilities.
- Never touches secrets here (env-only cookie is handled in drivers/tools).
"""

from __future__ import annotations

import logging
from typing import Any, Dict

from fastmcp import FastMCP  # type: ignore

from .tools import register_all_tools
from .logging_config import configure_logging
from .config.settings import SETTINGS

import os, logging

configure_logging(
     log_level=os.getenv("JOX_LOG_LEVEL", "INFO"),
     json_format=os.getenv("JOX_LOG_JSON", "0") in ("1", "true", "True"),
)
logger = logging.getLogger(__name__)


def create_mcp_server() -> FastMCP:
    """Create and configure the MCP server with all LinkedIn tools."""
    mcp = FastMCP("linkedin")

    # Register LinkedIn scraping tools
    register_all_tools(mcp)

    # Health check
    @mcp.tool()
    async def ping() -> Dict[str, Any]:
        """Lightweight health check."""
        return {"status": "ok", "service": "linkedin", "mode": "stdio"}

    # Session management
    @mcp.tool()
    async def close_session() -> Dict[str, Any]:
        """Close the current browser session and clean up resources."""
        try:
            from .drivers import close_all_drivers
            close_all_drivers()
            return {
                "status": "success",
                "message": "Closed browser session and cleaned up resources.",
            }
        except Exception as e:
            # Never leak secrets; just return the error message.
            return {"status": "error", "message": f"Error closing session: {e}"}

    return mcp


def shutdown_handler() -> None:
    """Clean up resources on shutdown."""
    try:
        from .drivers import close_all_drivers
        close_all_drivers()
    except Exception as e:
        logging.getLogger(__name__).warning("Shutdown cleanup encountered an error: %s", e)
