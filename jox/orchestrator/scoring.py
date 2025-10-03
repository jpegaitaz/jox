# jox/orchestrator/scoring.py

from __future__ import annotations

from typing import Dict, Any
import re
import logging

from jox.llm.openai_client import make_client, simple_json_chat
from jox.llm.prompts import SYSTEM_SCORER
from jox.settings import SETTINGS

logger = logging.getLogger(__name__)


def _normalize(text: str) -> str:
    """Collapse whitespace; keep it lightweight and dependency-free."""
    return " ".join((text or "").split())


def heuristic_overlap(cv_text: str, job_text: str) -> float:
    """
    Very fast Jaccard-like overlap over alphabetic 3+ char tokens.
    Returns a ratio in [0, 1].
    """
    cv_tokens = set(re.findall(r"[A-Za-z]{3,}", (cv_text or "").lower()))
    job_tokens = set(re.findall(r"[A-Za-z]{3,}", (job_text or "").lower()))
    if not job_tokens:
        return 0.0
    overlap = len(cv_tokens & job_tokens) / len(job_tokens)
    return min(1.0, max(0.0, overlap))


async def score_match(cv: Dict[str, Any], job: Dict[str, Any]) -> Dict[str, Any]:
    """
    Hybrid scoring:
      1) Ask LLM to return {"score": 0-10, "rationale": "..."}.
      2) If LLM fails or is empty, fall back to a heuristic overlap (0-10 scale).
    We also guard against empty job descriptions by synthesizing a minimal signal
    from title/company/location so scoring never degenerates to 0.00 across the board.
    """
    cv_text = _normalize(cv.get("raw", ""))
    jd = _normalize(job.get("description") or job.get("job_description") or "")
    jt = _normalize(job.get("title") or job.get("job_title") or "")
    comp = _normalize(job.get("company") or job.get("company_name") or "")
    loc = _normalize(job.get("location") or "")
    url = _normalize(job.get("job_url") or job.get("url") or "")

    # Synthesize a minimal, non-empty job text if description is missing.
    if not jd:
        jd = " ".join(filter(None, [jt, comp, loc]))
        logger.debug("score_match: missing description → synthesized text len=%d", len(jd))

    # Heuristic fallback (scaled to 0–10)
    # Use both the description and the (title+company+location) signal.
    h_desc = heuristic_overlap(cv_text, jd)
    h_meta = heuristic_overlap(cv_text, " ".join(filter(None, [jt, comp, loc])))
    heuristic_score = max(h_desc, h_meta) * 10.0

    # Build compact user message (trim to stay well within token budget)
    user = (
        f"CV:\n{cv_text[:6000]}\n\n"
        f"JOB [{jt or 'Unknown Title'} @ {comp or 'Unknown Company'} | {loc}]:\n"
        f"{jd[:6000]}\n\n"
        f"URL: {url}"
    )

    # Ask the model; if anything goes off the rails, we fall back safely.
    try:
        llm = make_client(SETTINGS.openai_model, temperature=0.1)
        data = await simple_json_chat(llm, SYSTEM_SCORER, user) or {}
        score_val = data.get("score", None)
        rationale = data.get("rationale", None)

        # Validate score; if missing/invalid, revert to heuristic.
        try:
            score = float(score_val)
        except (TypeError, ValueError):
            score = heuristic_score
            if rationale:
                rationale += f" | Fallback to heuristic={heuristic_score:.2f}"
            else:
                rationale = f"Heuristic overlap score {heuristic_score:.2f}"

        # Clamp to [0, 10]
        score = max(0.0, min(10.0, score))
        if rationale is None or not str(rationale).strip():
            rationale = f"Heuristic overlap score {heuristic_score:.2f}"

        return {"score": score, "rationale": rationale}

    except Exception as e:
        logger.warning("score_match: LLM scoring failed (%s); using heuristic=%.2f", e, heuristic_score)
        return {
            "score": max(0.0, min(10.0, heuristic_score)),
            "rationale": f"Heuristic overlap score {heuristic_score:.2f}",
        }
