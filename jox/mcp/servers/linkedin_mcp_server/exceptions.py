# src/linkedin_mcp_server/exceptions.py
# SPDX-License-Identifier: Apache-2.0
"""
Custom exceptions for LinkedIn MCP Server (JOX-hardened).

Defines hierarchical exception types for clearer failure categories:
- Authentication and cookie issues
- Driver initialization/runtime issues
- Transport misuse (HTTP disabled in JOX)
- Tool execution and rate limiting

Backwards compatible: retains original classes.
"""

class LinkedInMCPError(Exception):
    """Base exception for LinkedIn MCP Server."""
    pass


# --- Backwards-compatible exceptions (retained) ---
class CredentialsNotFoundError(LinkedInMCPError):
    """No credentials available in non-interactive mode (legacy)."""
    pass


class DriverInitializationError(LinkedInMCPError):
    """Failed to initialize Chrome WebDriver."""
    pass


# --- JOX-specific/auth-related exceptions ---
class AuthenticationMissingError(LinkedInMCPError):
    """Missing LINKEDIN_COOKIE in environment (env-only auth in JOX)."""
    pass


class InvalidCookieError(LinkedInMCPError):
    """Malformed or rejected LinkedIn cookie (li_at)."""
    pass


# --- Transport/Config exceptions ---
class HTTPTransportDisabledError(LinkedInMCPError):
    """Attempted to use 'streamable-http' transport, which JOX forbids."""
    pass


# --- Tool/runtime exceptions ---
class ToolExecutionError(LinkedInMCPError):
    """Wrapper for tool-level failures to provide consistent MCP responses."""
    def __init__(self, tool_name: str, message: str):
        super().__init__(f"{tool_name}: {message}")
        self.tool_name = tool_name
        self.message = message


class RateLimitedError(LinkedInMCPError):
    """Explicit signal when LinkedIn rate limiting is detected."""
    pass


__all__ = [
    "LinkedInMCPError",
    "CredentialsNotFoundError",
    "DriverInitializationError",
    "AuthenticationMissingError",
    "InvalidCookieError",
    "HTTPTransportDisabledError",
    "ToolExecutionError",
    "RateLimitedError",
]
