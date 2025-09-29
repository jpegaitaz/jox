# SPDX-License-Identifier: Apache-2.0
"""
LinkedIn MCP Server (vendored for JOX, hardened).

This package exposes a Model Context Protocol (MCP) toolset for LinkedIn:
- Person profiles
- Company data
- Job search and details

JOX hardening principles:
- Env-only authentication: set LINKEDIN_COOKIE='li_at=...'
- Local stdio transport only (no HTTP listeners)
- No keyring/credential storage, no interactive login
- Safer Selenium Chrome defaults; no remote debugging ports

Convenience:
- `create_mcp_server()` builds a FastMCP instance with all tools registered.

See:
- linkedin_mcp_server.server.create_mcp_server
- linkedin_mcp_server.tools.register_all_tools
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version as _pkg_version

# Expose a version if package metadata is present; otherwise fall back
try:
    __version__ = _pkg_version("linkedin_mcp_server")
except PackageNotFoundError:  # vendored/editable mode
    __version__ = "0.0.0+vendored"

# Convenience re-export for callers that want to spin up the MCP quickly
from .server import create_mcp_server  # noqa: E402

__all__ = ["__version__", "create_mcp_server"]
