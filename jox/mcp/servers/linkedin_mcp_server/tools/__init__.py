# src/linkedin_mcp_server/tools/__init__.py
# SPDX-License-Identifier: Apache-2.0
"""
LinkedIn scraping tools package (JOX-hardened).

Provides MCP tool implementations for LinkedIn data extraction:
- Person tools: LinkedIn profile scraping and analysis
- Company tools: Company profile and information extraction
- Job tools: Job posting details, search, and recommendations

Design:
- FastMCP integration for MCP-compliant tool registration
- Shared error handling via linkedin_mcp_server.error_handler
- Env-only authentication (LINKEDIN_COOKIE) through drivers facade
- Session persistence via a singleton Chrome driver (see drivers package)
"""

from __future__ import annotations

from fastmcp import FastMCP  # type: ignore

from .person import register_person_tools
from .company import register_company_tools
from .job import register_job_tools


def register_all_tools(mcp: FastMCP) -> None:
    """
    Register all LinkedIn MCP tools in one call.

    Usage:
        mcp = FastMCP("linkedin")
        register_all_tools(mcp)
    """
    register_person_tools(mcp)
    register_company_tools(mcp)
    register_job_tools(mcp)


__all__ = [
    "register_all_tools",
    "register_person_tools",
    "register_company_tools",
    "register_job_tools",
]
