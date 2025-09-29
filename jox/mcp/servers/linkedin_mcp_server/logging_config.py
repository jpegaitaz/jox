# linkedin_mcp_server/logging_config.py
# SPDX-License-Identifier: Apache-2.0
"""
Logging configuration for LinkedIn MCP Server (JOX-hardened).

- Optional JSON or compact formats.
- PII masking (e.g., LINKEDIN_COOKIE 'li_at=...') for ALL logs.
- Unified setup that reduces noise from selenium/urllib3.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict
# jox/mcp/servers/linkedin_mcp_server/config/logging_config.py



# Reuse the masking filter to guarantee secrets are never printed
COOKIE_RE = re.compile(r"(li_at=)([^; \n]+)", re.IGNORECASE)


class PIIMaskingFilter(logging.Filter):
    """Mask sensitive tokens like 'li_at=...' in all log messages & args."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = COOKIE_RE.sub(r"\1***", record.msg)
        if record.args:
            safe_args = []
            # Normalize tuple vs single value
            items = record.args if isinstance(record.args, tuple) else (record.args,)
            for a in items:
                if isinstance(a, str):
                    safe_args.append(COOKIE_RE.sub(r"\1***", a))
                else:
                    safe_args.append(a)
            record.args = tuple(safe_args)
        return True


class MCPJSONFormatter(logging.Formatter):
    """JSON formatter for MCP server logs with PII masking."""

    def format(self, record: logging.LogRecord) -> str:
        log_data: Dict[str, Any] = {
            "timestamp": self.formatTime(record),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        # Optional structured fields
        if hasattr(record, "error_type"):
            log_data["error_type"] = getattr(record, "error_type")
        if hasattr(record, "error_details"):
            log_data["error_details"] = getattr(record, "error_details")
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)
        # Final masking pass for anything that slipped via getMessage()
        def _mask(val: Any) -> Any:
            if isinstance(val, str):
                return COOKIE_RE.sub(r"\1***", val)
            if isinstance(val, dict):
                return {k: _mask(v) for k, v in val.items()}
            if isinstance(val, list):
                return [_mask(v) for v in val]
            return val
        return json.dumps(_mask(log_data))


class CompactFormatter(logging.Formatter):
    """Compact formatter (HH:MM:SS, shortened logger names) with PII masking."""

    def format(self, record: logging.LogRecord) -> str:
        # Copy to avoid mutating the original record
        record_copy = logging.LogRecord(
            name=record.name,
            level=record.levelno,
            pathname=record.pathname,
            lineno=record.lineno,
            msg=record.msg,
            args=record.args,
            exc_info=record.exc_info,
            func=record.funcName,
        )
        record_copy.stack_info = record.stack_info
        # Shorten package prefix for readability
        if record_copy.name.startswith("linkedin_mcp_server."):
            record_copy.name = record_copy.name[len("linkedin_mcp_server.") :]
        # Time as HH:MM:SS
        record_copy.asctime = self.formatTime(record_copy, datefmt="%H:%M:%S")
        # Ensure any message content is masked
        msg = COOKIE_RE.sub(r"\1***", record_copy.getMessage())
        return f"{record_copy.asctime} - {record_copy.name} - {logging.getLevelName(record_copy.levelno)} - {msg}"


def configure_logging(log_level: str = "INFO", json_format: bool = False) -> None:
    """
    Configure root logging with PII masking and selected formatter.

    Args:
        log_level: "DEBUG", "INFO", "WARNING", or "ERROR"
        json_format: True -> JSON logs; False -> compact human-readable
    """
    numeric_level = getattr(logging, log_level.upper(), logging.INFO)

    formatter: logging.Formatter = MCPJSONFormatter() if json_format else CompactFormatter()

    root = logging.getLogger()
    root.setLevel(numeric_level)

    # Remove existing handlers to avoid duplicates in notebooks/tests
    for h in root.handlers[:]:
        root.removeHandler(h)

    console = logging.StreamHandler()
    console.setFormatter(formatter)
    console.addFilter(PIIMaskingFilter())
    root.addHandler(console)

    # Quiet noisy libs
    logging.getLogger("selenium").setLevel(logging.ERROR)
    logging.getLogger("urllib3").setLevel(logging.ERROR)
    logging.getLogger("urllib3.connectionpool").setLevel(logging.ERROR)
