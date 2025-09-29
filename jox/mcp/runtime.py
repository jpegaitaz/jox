from __future__ import annotations
import asyncio
from typing import Any, Dict, List

# For simplicity we directly call the vendored server via FastMCP client API
# If you prefer subprocess stdio, adapt here.

try:
    from fastmcp import Client  # type: ignore
except Exception:  # pragma: no cover
    Client = None  # type: ignore

class MCPRuntime:
    def __init__(self):
        if Client is None:
            raise RuntimeError("fastmcp is required")
        # Assuming the vendored server is importable; otherwise spawn a subprocess
        self.client = Client("linkedin")

    async def call(self, tool_name: str, **kwargs) -> Any:
        return await self.client.call(tool_name, **kwargs)
