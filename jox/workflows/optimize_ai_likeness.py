from __future__ import annotations
import logging
from typing import Dict, Any, List, Tuple

from jox.llm.openai_client import make_client, simple_json_chat, simple_text_chat
from jox.llm.prompts import SYSTEM_HUMANIZE_CONSTRAINED
from jox.cv.render import render_cv_pdf, render_cover_letter_pdf
from jox.utils.dates import today_compact
from jox.settings import SETTINGS
from jox.quality.ai_likeness_client import analyze_text_ai, heuristic_humanize

logger = logging.getLogger(__name__)

def _extract_editable_texts(cv_json: Dict[str, Any], cl_json: Dict[str, Any]) -> Dict[str, str]:
    """
    Pull out the main free-text fields we want to optimize.
    Adjust keys to match your cv_data JSON shape.
    """
    texts: Dict[str, str] = {}
    # CV
    header_sum = (cv_json.get("summary") or cv_json.get("profile") or "").strip()
    texts["cv_summary"] = header_sum

    # Experience bullets joined; we’ll rewrite then split back on ' • ' markers
    exps = cv_json.get("experience") or []
    exp_blobs: List[str] = []
    for exp in exps:
        bullets = exp.get("bullets") or exp.get("highlights") or []
        if isinstance(bullets, list) and bullets:
            exp_blobs.append("\n".join(bullets))
    texts["cv_experience_bullets"] = "\n".join(exp_blobs).strip()

    # Cover letter
    texts["cover_letter_body"] = (cl_json.get("body") or "").strip()
    return texts

def _apply_texts_back(cv_json: Dict[str, Any], cl_json: Dict[str, Any], rewritten: Dict[str, str]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    # CV summary
    if "cv_summary" in rewritten and rewritten["cv_summary"]:
        if "summary" in cv_json:
            cv_json["summary"] = rewritten["cv_summary"]
        elif "profile" in cv_json:
            cv_json["profile"] = rewritten["cv_summary"]

    # CV experience bullets
    if "cv_experience_bullets" in rewritten and rewritten["cv_experience_bullets"]:
        # naive split on newlines back to bullets
        new_bullets_all = [b.strip("• ").strip() for b in rewritten["cv_experience_bullets"].split("\n") if b.strip()]
        exps = cv_json.get("experience") or []
        idx = 0
        for exp in exps:
            bullets = exp.get("bullets") or exp.get("highlights") or []
            if isinstance(bullets, list) and bullets:
                take = len(bullets)
                exp["bullets"] = new_bullets_all[idx:idx+take] or bullets
                idx += take

    # Cover letter body
    if "cover_letter_body" in rewritten and rewritten["cover_letter_body"]:
        cl_json["body"] = rewritten["cover_letter_body"]

    return cv_json, cl_json

async def _analyze_bundle(texts: Dict[str, str]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for k, v in texts.items():
        res = await analyze_text_ai(v or "")
        out[k] = res["overall"]["ai_likeness_percent"]
    # Weighted overall: CL body a bit heavier (screened more often)
    overall = round(0.4*out.get("cover_letter_body", 0) + 0.35*out.get("cv_experience_bullets", 0) + 0.25*out.get("cv_summary", 0))
    out["_overall"] = int(overall)
    return out

async def _rewrite_pass(llm, texts: Dict[str, str], target: int, analysis: Dict[str, Any]) -> Dict[str, str]:
    """
    One pass:
      - Heuristic humanize first (cheap)
      - LLM constrained rewrite second (precise), passing the text that still scores high.
    """
    # Heuristic
    heur = {k: (heuristic_humanize(v, target_percent=target) if v else v) for k, v in texts.items()}

    # Analyze post-heuristic
    heur_scores = await _analyze_bundle(heur)

    rewritten: Dict[str, str] = {}
    for key, val in heur.items():
        if key.startswith("_"):  # skip meta
            continue
        # If still above target by more than 5 points → use LLM constrained rewrite
        cur_score = heur_scores.get(key, 0)
        if cur_score > (target + 5) and val:
            prompt = f"{val}"
            new_text = await simple_text_chat(llm, SYSTEM_HUMANIZE_CONSTRAINED, prompt)
            rewritten[key] = new_text.strip()
        else:
            rewritten[key] = val

    return rewritten

async def optimize_and_render(
    cv_json: Dict[str, Any],
    cl_json: Dict[str, Any],
    job_title_fs: str,
    artifacts_dir: str,
    *,
    target_percent: int = 35,
    max_iters: int = 4,
) -> Dict[str, Any]:
    """
    Iteratively reduce AI-likeness on key text regions, then render PDFs.
    Returns paths and a small summary.
    """
    llm = make_client(SETTINGS.openai_model, temperature=0.2)

    texts = _extract_editable_texts(cv_json, cl_json)
    history: List[Dict[str, Any]] = []

    for it in range(1, max_iters+1):
        scores = await _analyze_bundle(texts)
        history.append({"iter": it, "scores": scores})
        overall = scores["_overall"]
        logger.info("AI-likeness iteration %d: overall=%d%% (details: %s)", it, overall, scores)

        if overall <= target_percent:
            break

        # Rewrite pass
        texts = await _rewrite_pass(llm, texts, target_percent, scores)

    # Final analyze after loop
    final_scores = await _analyze_bundle(texts)
    history.append({"iter": len(history)+1, "scores": final_scores})

    # Commit texts back into the JSON structures
    cv_json, cl_json = _apply_texts_back(cv_json, cl_json, texts)

    # Render PDFs
    date = today_compact()
    cv_path = f"{artifacts_dir}/cv_{job_title_fs}_{date}.pdf"
    cl_path = f"{artifacts_dir}/coverletter_{job_title_fs}_{date}.pdf"
    render_cv_pdf(cv_path, job_title_fs, cv_json)
    render_cover_letter_pdf(cl_path, job_title_fs, cl_json)

    return {
        "cv_path": cv_path,
        "cover_letter_path": cl_path,
        "final_overall_percent": final_scores["_overall"],
        "per_section_percent": final_scores,
        "iterations": history,
    }
