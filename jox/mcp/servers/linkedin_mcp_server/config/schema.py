# src/linkedin_mcp_server/config/schema.py
# SPDX-License-Identifier: Apache-2.0
"""
Configuration schema definitions for JOX-hardened LinkedIn MCP integration.

Compatibility:
- Preserves original dataclass names/fields to avoid breaking imports.
Hardening:
- STDIO-only: "streamable-http" is rejected during validation.
- No credentials flow: email/password fields remain but are unused.
- Safer defaults (lazy_init=False, log_level=INFO).
"""

from dataclasses import dataclass, field
from typing import List, Literal, Optional


class ConfigurationError(Exception):
    """Raised when configuration validation fails."""
    pass


@dataclass
class ChromeConfig:
    """Configuration for Chrome driver."""
    headless: bool = True
    chromedriver_path: Optional[str] = None
    browser_args: List[str] = field(default_factory=list)
    user_agent: Optional[str] = None


@dataclass
class LinkedInConfig:
    """LinkedIn connection configuration (env-only cookie in JOX)."""
    # Retained for compatibility — JOX does not use these.
    email: Optional[str] = None
    password: Optional[str] = None

    # Primary auth input (expected via env: LINKEDIN_COOKIE='li_at=...').
    cookie: Optional[str] = None

    def cookie_looks_valid(self) -> bool:
        """Lightweight shape check; not a strict validator."""
        if not self.cookie:
            return False
        c = self.cookie.strip().lower()
        return c.startswith("li_at=") and len(c) > len("li_at=")


@dataclass
class ServerConfig:
    """MCP server configuration (JOX: stdio-only)."""
    transport: Literal["stdio", "streamable-http"] = "stdio"
    transport_explicitly_set: bool = False
    # Deterministic by default in JOX
    lazy_init: bool = False
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    # Disabled in JOX (retained for compatibility)
    get_cookie: bool = False
    clear_keychain: bool = False

    # HTTP transport config (inert in JOX)
    host: str = "127.0.0.1"
    port: int = 8000
    path: str = "/mcp"


@dataclass
class AppConfig:
    """Main application configuration."""
    chrome: ChromeConfig = field(default_factory=ChromeConfig)
    linkedin: LinkedInConfig = field(default_factory=LinkedInConfig)
    server: ServerConfig = field(default_factory=ServerConfig)
    is_interactive: bool = field(default=False)

    def __post_init__(self) -> None:
        """Validate configuration after initialization."""
        self._validate_transport_config()
        self._validate_port_range()
        self._validate_path_format()

    def _validate_transport_config(self) -> None:
        """Validate transport configuration is consistent (JOX forbids HTTP)."""
        if self.server.transport == "streamable-http":
            # In JOX, HTTP transport is not allowed.
            raise ConfigurationError(
                "HTTP transport ('streamable-http') is disabled in JOX. Use 'stdio' only."
            )

    def _validate_port_range(self) -> None:
        """Validate port range only if HTTP were enabled (kept for compatibility)."""
        # Since HTTP is disallowed above, this is effectively inert, but we keep
        # it to preserve original behavior if someone refactors in the future.
        if not (1 <= self.server.port <= 65535):
            raise ConfigurationError(
                f"Port {self.server.port} is not in valid range (1-65535)"
            )

    def _validate_path_format(self) -> None:
        """Validate path format for HTTP transport (inert in JOX)."""
        if self.server.transport == "streamable-http":
            if not self.server.path.startswith("/"):
                raise ConfigurationError(
                    f"HTTP path '{self.server.path}' must start with '/'"
                )
            if len(self.server.path) < 2:
                raise ConfigurationError(
                    f"HTTP path '{self.server.path}' must be at least 2 characters"
                )
