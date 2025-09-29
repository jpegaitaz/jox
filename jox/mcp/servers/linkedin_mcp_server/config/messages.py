# linkedin_mcp_server/config/messages.py
# SPDX-License-Identifier: Apache-2.0
"""
Centralized message formatting for JOX-hardened LinkedIn MCP integration.

- Env-only auth (LINKEDIN_COOKIE='li_at=...').
- No keyring/credential storage.
- No interactive get-cookie flow.
- Consistent, PII-safe messages.
"""

from __future__ import annotations


def _mask_cookie_sample(s: str, show: int = 6) -> str:
    if not s:
        return ""
    # Reveal only a tiny prefix to aid debugging
    prefix = s[:show]
    return f"{prefix}***"


class ErrorMessages:
    """Centralized error message formatting for consistent communication."""

    @staticmethod
    def no_cookie_found(is_interactive: bool) -> str:
        """
        No LinkedIn cookie was found in the environment.
        Args:
            is_interactive: Kept for signature compatibility; not used to change guidance.
        """
        return (
            "No LinkedIn authentication found.\n"
            "Please set the environment variable LINKEDIN_COOKIE with your session token, e.g.:\n"
            "  LINKEDIN_COOKIE='li_at=YOUR_TOKEN_HERE'\n"
            "Notes:\n"
            "  • JOX does not support email/password login or keychain storage.\n"
            "  • The cookie is read from the environment only and never persisted."
        )

    @staticmethod
    def invalid_cookie_format(cookie_sample: str) -> str:
        safe = _mask_cookie_sample(cookie_sample)
        return (
            f"Invalid LinkedIn cookie format: '{safe}'.\n"
            "Expected format: LINKEDIN_COOKIE='li_at=…'"
        )

    @staticmethod
    def unsupported_credentials_flow() -> str:
        return (
            "Credentials-based login is disabled in JOX.\n"
            "Provide a valid session cookie via LINKEDIN_COOKIE instead."
        )

    @staticmethod
    def unsupported_storage_flow() -> str:
        return (
            "Storing cookies or credentials in a keychain/keyring is disabled in JOX.\n"
            "Use env-only LINKEDIN_COOKIE; secrets are never persisted."
        )


class InfoMessages:
    """Centralized informational message formatting."""

    @staticmethod
    def using_cookie_from_environment() -> str:
        return "Using LinkedIn cookie from environment (masked)."

    @staticmethod
    def cookie_masked_preview(cookie: str) -> str:
        return f"LINKEDIN_COOKIE preview: { _mask_cookie_sample(cookie) }"

    @staticmethod
    def headless_mode(enabled: bool) -> str:
        return f"Headless mode: {'ON' if enabled else 'OFF'}"

    @staticmethod
    def chromedriver_path(path: str | None) -> str:
        return f"ChromeDriver: {path or 'auto-detected or selenium-manager'}"
