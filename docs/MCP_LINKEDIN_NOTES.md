# MCP: LinkedIn Notes

JOX vendors a hardened LinkedIn MCP server (env-only cookie, stdio-only). The tool adapters
use `fastmcp.Client("linkedin")`. Ensure the server is started within the same process or
as an external process bound to stdio.
