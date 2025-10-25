from __future__ import annotations
from typing import Dict, Any, List

# Local import from the MCP server package (no network / no API keys)
from ai_textscan_mcp_server.detector import analyze_text as _analyze_text
from ai_textscan_mcp_server.detector import humanize_text as _heur_humanize

async def analyze_text_ai(text: str) -> Dict[str, Any]:
    return await _analyze_text(text)

def heuristic_humanize(text: str, target_percent: int = 35) -> str:
    return _heur_humanize(text, target_percent=target_percent)
