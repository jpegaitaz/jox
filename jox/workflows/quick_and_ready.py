from __future__ import annotations
from typing import Dict, Any
from jox.orchestrator.agent import Orchestrator
from jox.orchestrator.report import write_session_report

async def run_quick_and_ready(cv: Dict[str, Any], function: str, role: str, country: str) -> Dict[str, Any]:
    orch = Orchestrator()
    result = await orch.quick_and_ready(cv, function, role, country)
    report_path = write_session_report("outputs/reports", result)
    result["report_path"] = report_path
    return result
