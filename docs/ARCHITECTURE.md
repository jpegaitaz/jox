# JOX Architecture

- **CLI (Terminal)**: `jox/cli.py` greeting, inputs, and workflow launch.
- **Orchestrator**: `jox/orchestrator/agent.py` coordinates MCP tools and LLM steps.
- **Memory**: `data/entries.json` and `data/outcomes.json` persisted and referenced.
- **MCP Runtime**: `jox/mcp/tool_adapters.py` wraps LinkedIn MCP tools.
- **CV**: parsing and rendering modules.
- **Reports**: per-session JSON with counts and scores.

Security: env-only cookie, stdio-only MCP, PII-masked logging.
