# jox/mcp/servers/linkedin_mcp_server/config/logging_config.py
from ..logging_config import configure_logging as _configure_logging

def configure_logger(level: str = "INFO", json_format: bool = False):
    # Adapt old signature (level=...) to new one (log_level=...)
    return _configure_logging(log_level=level, json_format=json_format)

# Optional: also re-export the new name for callers that use it directly
configure_logging = _configure_logging
