# jox/workflows/quick_and_ready.py
from __future__ import annotations
from typing import Dict, Any, Optional

from jox.orchestrator.agent import Orchestrator
from jox.orchestrator.report import write_session_report
from jox.settings import SETTINGS


async def run_quick_and_ready(
    cv: Dict[str, Any],
    function: str,
    role: str,
    country: str,
    *,
    ai_target: Optional[int] = None,       # e.g., 35
    ai_max_iters: Optional[int] = None,    # e.g., 4
) -> Dict[str, Any]:
    """
    Runs the main workflow:
      1) search/enrich/score/shortlist
      2) generate CV + CL JSON
      3) optimize AI-likeness (optional, via ai_target/ai_max_iters)
      4) render PDFs
      5) write a session report
    """
    # Make these knobs visible to any component reading SETTINGS (best-effort).
    if ai_target is not None:
        try:
            setattr(SETTINGS, "ai_likeness_target", int(ai_target))
        except Exception:
            pass
    if ai_max_iters is not None:
        try:
            setattr(SETTINGS, "ai_likeness_max_iters", int(ai_max_iters))
        except Exception:
            pass

    orch = Orchestrator()
    result = await orch.quick_and_ready(
        cv,
        function,
        role,
        country,
        ai_target=ai_target,
        ai_max_iters=ai_max_iters,
    )

    # Persist a human-friendly report (includes full vacancy descriptions and AI-Guard traces)
    report_path = write_session_report("outputs/reports", result)
    result["report_path"] = report_path
    return result
