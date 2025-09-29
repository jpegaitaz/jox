# src/linkedin_mcp_server/error_handler.py
# SPDX-License-Identifier: Apache-2.0
"""
Centralized error handling for LinkedIn MCP Server with structured responses (JOX-hardened).

- Env-only authentication (LINKEDIN_COOKIE). No keyring, no email/password prompts.
- Consistent MCP error payloads for tools returning dicts or lists.
- Safe driver acquisition helper that uses env-only cookie.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

# Tolerate absence of linkedin_scraper; define fallbacks so this module imports cleanly
try:
    from .exceptions import (  # type: ignore
        CaptchaRequiredError,
        InvalidCredentialsError,
        LoginTimeoutError,
        RateLimitError,
        SecurityChallengeError,
        TwoFactorAuthError,
    )
except Exception:  # pragma: no cover
    class _E(RuntimeError): ...
    class CaptchaRequiredError(_E): ...
    class InvalidCredentialsError(_E): ...
    class LoginTimeoutError(_E): ...
    class RateLimitError(_E): ...
    class SecurityChallengeError(_E): ...
    class TwoFactorAuthError(_E): ...

from .exceptions import (
    AuthenticationMissingError,
    CredentialsNotFoundError,   # legacy, kept for compatibility
    HTTPTransportDisabledError,
    InvalidCookieError,
    LinkedInMCPError,
    ToolExecutionError,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public error-handling helpers
# ---------------------------------------------------------------------------
def handle_tool_error(exception: Exception, context: str = "") -> Dict[str, Any]:
    """
    Handle errors from tool functions and return a structured response dict.
    """
    return convert_exception_to_response(exception, context)


def handle_tool_error_list(exception: Exception, context: str = "") -> List[Dict[str, Any]]:
    """
    Handle errors from tool functions that return lists.
    """
    return [convert_exception_to_response(exception, context)]


# ---------------------------------------------------------------------------
# Exception → MCP payload mapping
# ---------------------------------------------------------------------------
def convert_exception_to_response(exception: Exception, context: str = "") -> Dict[str, Any]:
    """
    Convert an exception to a structured MCP response (dict).
    """
    # --- Auth/config errors (env-only in JOX) ---
    if isinstance(exception, (AuthenticationMissingError, CredentialsNotFoundError)):
        return {
            "error": "authentication_not_found",
            "message": "LinkedIn authentication is missing.",
            "resolution": "Set LINKEDIN_COOKIE in the environment: li_at=YOUR_SESSION_TOKEN",
            "context": context,
        }

    if isinstance(exception, InvalidCookieError) or isinstance(exception, InvalidCredentialsError):
        return {
            "error": "invalid_cookie",
            "message": "The provided LinkedIn cookie appears invalid or expired.",
            "resolution": "Update LINKEDIN_COOKIE (li_at=...) and try again.",
            "context": context,
        }

    if isinstance(exception, HTTPTransportDisabledError):
        return {
            "error": "transport_disabled",
            "message": "HTTP transport is disabled in JOX. Use stdio transport only.",
            "context": context,
        }

    # --- LinkedIn site-specific hurdles ---
    if isinstance(exception, CaptchaRequiredError):
        return {
            "error": "captcha_required",
            "message": "LinkedIn requested a captcha challenge.",
            "resolution": "Complete the captcha in a normal browser and refresh your session cookie.",
            "context": context,
        }

    if isinstance(exception, SecurityChallengeError):
        return {
            "error": "security_challenge_required",
            "message": "LinkedIn triggered a security challenge.",
            "resolution": "Complete the challenge in a normal browser and refresh your session cookie.",
            "context": context,
        }

    if isinstance(exception, TwoFactorAuthError):
        return {
            "error": "two_factor_auth_required",
            "message": "Two-factor authentication is required.",
            "resolution": "Complete 2FA in a normal browser and refresh your session cookie.",
            "context": context,
        }

    if isinstance(exception, RateLimitError):
        return {
            "error": "rate_limited",
            "message": "LinkedIn rate-limited your requests.",
            "resolution": "Wait a few minutes and try again; reduce request frequency.",
            "context": context,
        }

    if isinstance(exception, LoginTimeoutError):
        return {
            "error": "login_timeout",
            "message": "Login/navigation timed out.",
            "resolution": "Check network connectivity and verify LINKEDIN_COOKIE is valid.",
            "context": context,
        }

    # --- Our generic wrapper for tool failures ---
    if isinstance(exception, ToolExecutionError):
        return {
            "error": "tool_error",
            "message": exception.message,
            "tool": exception.tool_name,
            "context": context,
        }

    # --- Catch-all for LinkedInMCPError subclasses ---
    if isinstance(exception, LinkedInMCPError):
        return {
            "error": "linkedin_error",
            "message": str(exception),
            "context": context,
        }

    # --- Unknown/unexpected errors ---
    logger.error(
        "Unhandled error in %s: %s",
        context or "<unknown>",
        exception,
        extra={
            "error_type": type(exception).__name__,
            "error_details": str(exception),
        },
        exc_info=True,
    )
    return {
        "error": "unknown_error",
        "message": f"Failed to execute {context or 'operation'}: {str(exception)}",
        "context": context,
    }


# ---------------------------------------------------------------------------
# Safe driver acquisition (env-only)
# ---------------------------------------------------------------------------
def safe_get_driver():
    """
    Safely get or create an authenticated driver using env-only LINKEDIN_COOKIE.

    Returns:
        A Selenium WebDriver instance

    Raises:
        LinkedInMCPError (or subclass) for auth/driver issues
    """
    try:
        from .drivers import get_or_create_driver_env
        return get_or_create_driver_env()
    except (AuthenticationMissingError, InvalidCookieError) as e:
        # Re-raise known auth failures as-is for clean mapping
        raise e
    except Exception as e:
        # Wrap any other issues to keep tool code simple
        raise LinkedInMCPError(f"Driver acquisition failed: {e}")
