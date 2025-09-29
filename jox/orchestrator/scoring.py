from __future__ import annotations
from typing import Dict, Any
import re
from jox.llm.openai_client import make_client, simple_json_chat
from jox.llm.prompts import SYSTEM_SCORER
from jox.settings import SETTINGS

def heuristic_overlap(cv_text: str, job_text: str) -> float:
    cv_tokens = set(re.findall(r"[A-Za-z]{3,}", cv_text.lower()))
    job_tokens = set(re.findall(r"[A-Za-z]{3,}", job_text.lower()))
    if not job_tokens:
        return 0.0
    overlap = len(cv_tokens & job_tokens) / len(job_tokens)
    return min(1.0, overlap)

async def score_match(cv: Dict[str, Any], job: Dict[str, Any]) -> Dict[str, Any]:
    cv_text = cv.get("raw", "")
    jd = job.get("description") or job.get("job_description") or ""
    jt = job.get("title") or job.get("job_title") or ""
    comp = job.get("company") or job.get("company_name") or ""
    user = f"CV:\n{cv_text[:6000]}\n\nJOB [{jt} @ {comp}]:\n{jd[:6000]}"
    llm = make_client(SETTINGS.openai_model, temperature=0.1)
    fallback = heuristic_overlap(cv_text, jd) * 10.0
    data = await simple_json_chat(llm, SYSTEM_SCORER, user)
    score = float(data.get("score", fallback))
    rationale = data.get("rationale", f"Heuristic overlap score {fallback:.1f}")
    score = max(0.0, min(10.0, score))
    return {"score": score, "rationale": rationale}
