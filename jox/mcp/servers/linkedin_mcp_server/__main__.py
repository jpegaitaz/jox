#!/usr/bin/env python3
"""Entry point for linkedin-mcp-server command (JOX-hardened)."""

import logging
import sys

from .cli_main import main

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(0)
    except Exception as e:
        logging.getLogger(__name__).error("Fatal error: %s", e, exc_info=True)
        print(f"❌ Error running MCP server: {e}")
        sys.exit(1)
