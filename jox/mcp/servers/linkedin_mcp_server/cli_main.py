# JOX-hardened CLI for the vendored LinkedIn MCP server (stdio only)
from __future__ import annotations
import io
import logging
import os
import sys

from .logging_config import configure_logging
from .server import create_mcp_server, shutdown_handler
from .drivers import close_all_drivers
from .config.secrets import Secrets

# Ensure stdout is UTF-8
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

logger = logging.getLogger(__name__)


def get_version() -> str:
    try:
        import tomllib
        here = os.path.dirname(os.path.dirname(__file__))  # package root
        pyproject = os.path.join(here, "pyproject.toml")
        with open(pyproject, "rb") as f:
            data = tomllib.load(f)
        return data.get("project", {}).get("version", "unknown")
    except Exception:
        return "unknown"


def ensure_authentication_ready() -> str:
    """
    JOX mode: require env cookie (LINKEDIN_COOKIE). No interactive fallback.
    """
    cookie = Secrets.get_cookie()  # raises with a clear message if missing/malformed
    logger.info("Using LinkedIn cookie from environment (masked).")
    return cookie


def exit_gracefully(exit_code: int = 0) -> None:
    """Exit the application gracefully, cleaning up resources."""
    print("👋 Shutting down LinkedIn MCP server...")
    try:
        close_all_drivers()
    finally:
        try:
            shutdown_handler()
        finally:
            sys.exit(exit_code)


def main() -> None:
    # Configure logging from env
    log_level = os.getenv("JOX_LOG_LEVEL", "INFO")
    default_json = "0" if sys.stdout.isatty() else "1"
    json_logs = os.getenv("JOX_LOG_JSON", default_json) in ("1", "true", "True")
    configure_logging(log_level=log_level, json_format=json_logs)

    version = get_version()
    logging.getLogger(__name__).info("🔗 LinkedIn MCP Server v%s (JOX)", version)

    # Phase 1: Authentication (env first)
    try:
        _ = ensure_authentication_ready()
        logging.getLogger(__name__).info("Authentication ready (env cookie).")
    except KeyboardInterrupt:
        print("\n👋 Setup cancelled by user")
        exit_gracefully(0)
    except Exception as e:
        print(f"❌ Cookie required. Set LINKEDIN_COOKIE (li_at=...) in your environment. Details: {e}")
        exit_gracefully(1)

    # Phase 2: Driver init — JOX always uses lazy init (created on first tool call)
    # (Nothing to do here.)

    # Phase 3: Start MCP server (STDIO only for JOX)
    try:
        mcp = create_mcp_server()
        print("\n🚀 Running LinkedIn MCP server (STDIO mode)...")
        mcp.run(transport="stdio")
    except KeyboardInterrupt:
        print("\n⏹️  Server stopped by user")
        exit_gracefully(0)
    except Exception as e:
        logging.getLogger(__name__).error("Fatal error running MCP server: %s", e, exc_info=True)
        print(f"❌ Error running MCP server: {e}")
        exit_gracefully(1)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        exit_gracefully(0)
    except Exception as e:
        logging.getLogger(__name__).error("Fatal error running MCP server: %s", e, exc_info=True)
        print(f"❌ Error running MCP server: {e}")
        exit_gracefully(1)
