# jox/orchestrator/agent.py
from __future__ import annotations

import os
import inspect
import logging
import uuid
from typing import Dict, Any, List
import asyncio
import re as _re

from jox.orchestrator.scoring import score_match
from jox.orchestrator.memory import knowledge_snapshot, add_outcome
from jox.cv.render import render_cv_pdf, render_cover_letter_pdf
from jox.llm.openai_client import make_client, simple_json_chat
from jox.llm.prompts import SYSTEM_COVER_LETTER_JSON, SYSTEM_CV_UPDATE_JSON
from jox.settings import SETTINGS
from jox.utils.dates import today_compact
from jox.mcp.tool_adapters import get_job_tools

logger = logging.getLogger(__name__)
ARTIFACTS_DIR = "outputs/artifacts"

# --- AI-Guard (log what we actually loaded for easier diagnosis)
from jox.ai_guard.optimizer import reduce_ai_likeness, evaluate_ai_likeness  # noqa: F401
import inspect as _inspect
from jox.ai_guard import optimizer as _aiopt
logger.info("AI-Guard optimizer module: %s", getattr(_aiopt, "__file__", "<?>"))
logger.info("AI-Guard reduce_ai_likeness signature: %s", _inspect.signature(_aiopt.reduce_ai_likeness))


async def _maybe_await(callable_or_coro, *args, **kwargs):
    """
    - If given a coroutine object: await it.
    - If given a callable: call it and await the result if it's awaitable.
    """
    if asyncio.iscoroutine(callable_or_coro):
        return await callable_or_coro
    res = callable_or_coro(*args, **kwargs)
    if inspect.isawaitable(res) or asyncio.iscoroutine(res):
        return await res
    return res


# ---------- Cover-letter helpers (synthesis + closing normalization) ----------
def _split_coverletter_sections(full_text: str) -> Dict[str, str]:
    """
    Naive splitter:
      - paragraphs = split on blank lines
      - intro  = first paragraph
      - closing = last paragraph (strip a trailing 'PS:' paragraph)
      - ps     = last paragraph starting with 'PS' (optional)
      - body   = everything between intro and closing
    """
    import re
    if not full_text or not full_text.strip():
        return {}
    paras = [p.strip() for p in re.split(r"\n\s*\n", full_text.strip()) if p.strip()]
    if not paras:
        return {}

    ps = ""
    if paras and paras[-1].lower().startswith(("ps:", "ps ")):
        ps = paras.pop(-1).strip()

    intro = paras[0] if paras else ""
    closing = paras[-1] if len(paras) > 1 else ""
    body = "\n\n".join(paras[1:-1]) if len(paras) > 2 else ""

    out: Dict[str, str] = {}
    if intro:
        out["intro"] = intro
    if body:
        out["body"] = body
    if closing:
        out["closing"] = closing
    if ps:
        out["ps"] = ps
    return out


def _collect_text_parts(cl_data: Dict[str, Any]) -> Dict[str, str]:
    """
    Ensure we have intro/body/closing/ps by:
      1) Using explicit fields when present
      2) Falling back to 'plain_text' by splitting it
      3) Returning only non-empty parts
    """
    parts = {k: (cl_data.get(k) or "").strip() for k in ("intro", "body", "closing", "ps")}
    have_any = any(bool(v) for v in parts.values())
    if not have_any:
        pt = (cl_data.get("plain_text") or "").strip()
        if pt:
            synthesized = _split_coverletter_sections(pt)
            for k, v in synthesized.items():
                if v and not parts.get(k):
                    parts[k] = v
            # also write back once so it persists in rendered PDFs
            for k, v in synthesized.items():
                if v and not cl_data.get(k):
                    cl_data[k] = v
    return {k: v for k, v in parts.items() if v}


_VAL_RX = _re.compile(
    r"^\s*(Kind regards|Best regards|Regards|Sincerely|Yours sincerely|Yours faithfully|"
    r"Cordialement|Bien à vous|Meilleures salutations|Saludos cordiales|Saludos|Atte)\b[ ,:]*",
    _re.IGNORECASE,
)

def _split_valediction_runon(s: str) -> tuple[str, str]:
    """
    If 'closing' contains a valediction followed by more prose, split it:
      returns (pure_valediction_line, remainder_text)
    """
    if not s:
        return "", ""
    txt = s.strip()
    m = _VAL_RX.match(txt)
    if not m:
        return txt, ""
    val_line = m.group(0).rstrip(",: ").strip()
    rest = txt[m.end():].strip()
    # If rest starts with punctuation or is very short, ignore
    if rest and not rest.startswith((",", ";")):
        return val_line, rest
    return val_line, ""


def _append_to_body(cl_data: Dict[str, Any], extra: str) -> None:
    if not extra:
        return
    body = (cl_data.get("body") or "").strip()
    cl_data["body"] = (body + ("\n\n" if body else "") + extra).strip()


# --------------------------------- Orchestrator ---------------------------------
class Orchestrator:
    """Search → enrich → score → shortlist → generate artifacts (with AI-Guard)."""

    def __init__(self) -> None:
        source = getattr(SETTINGS, "job_source", None) or os.getenv("JOB_SOURCE", "indeed")
        self.jobs = get_job_tools(source)

    async def _fetch_details_best_effort(self, listing: Dict[str, Any]) -> Dict[str, Any]:
        """If the adapter exposes get_job_details, enrich the listing; else return listing."""
        job_id_or_url = listing.get("job_url") or listing.get("url") or listing.get("id") or ""
        if not job_id_or_url or not hasattr(self.jobs, "get_job_details"):
            return listing
        try:
            details = await _maybe_await(self.jobs.get_job_details, job_id_or_url)
            details.setdefault("title", listing.get("title"))
            details.setdefault("company", listing.get("company"))
            details.setdefault("job_url", listing.get("job_url") or listing.get("url"))
            return details
        except Exception as e:
            logger.debug("get_job_details failed (%s); using listing only.", e)
            return listing

    def _guard_reduce(self, text: str, *, target: int | None, iters: int | None, label: str):
        """
        Compatibility shim around reduce_ai_likeness:
        - Prefer new signature: reduce_ai_likeness(text, target_pct=..., max_iters=..., label=...)
        - If a legacy 1-arg function exists, log + no-op (but record baseline)
        - Never raises; always returns (optimized_text, log_dict)
        """
        try:
            from jox.ai_guard.optimizer import reduce_ai_likeness as _reduce, evaluate_ai_likeness as _eval
        except Exception as e:
            logger.warning("AI-Guard unavailable for %s (%s); leaving text unchanged.", label, e)
            return text, {"label": label, "note": "ai_guard_unavailable"}

        try:
            return _reduce(text, target_pct=target, max_iters=iters, label=label)
        except TypeError as e:
            try:
                base = float(_eval(text))
            except Exception:
                base = None
            logger.warning("AI-Guard legacy fallback for %s: %s", label, e)
            return text, {
                "label": label,
                "target": target,
                "max_iters": iters,
                "runs": [{"iter": 0, "score": base if base is not None else -1, "note": "legacy_no_opt"}],
            }
        except Exception as e:
            logger.warning("AI-Guard error for %s: %s (leaving text unchanged)", label, e)
            return text, {
                "label": label,
                "target": target,
                "max_iters": iters,
                "runs": [{"iter": 0, "score": -1, "note": f"error:{e}"}],
            }

    async def quick_and_ready(
        self,
        cv: Dict[str, Any],
        function: str,
        role: str,
        country: str,
        *,
        ai_target: int | None = None,
        ai_max_iters: int | None = None,
    ) -> Dict[str, Any]:
        # Ensure artifacts directory exists
        os.makedirs(ARTIFACTS_DIR, exist_ok=True)

        session_id = str(uuid.uuid4())
        search_term = " ".join(x for x in [(role or "").strip(), (function or "").strip()] if x)

        # 1) SEARCH ———
        logger.info("Starting QuickAndReady: query='%s' location='%s'", search_term, country)
        jobs: List[Dict[str, Any]] = await _maybe_await(
            self.jobs.search_jobs,
            search_term=search_term,
            location=country,
            days=7,           # adapters that don't use 'days' should ignore it
            limit=30,
            country=country,  # some adapters use this to pick domain/locale
        )
        num_results = len(jobs)
        logger.info("Search returned %d listings", num_results)

        # 2) ENRICH + SCORE ———
        THRESHOLD: float = float(getattr(SETTINGS, "compatibility_threshold", 7.5))
        MAX_DOCS: int = int(getattr(SETTINGS, "max_docs", 5))

        shortlisted: List[Dict[str, Any]] = []
        scored_rows: List[Dict[str, Any]] = []

        for listing in jobs[:30]:
            details = await self._fetch_details_best_effort(listing)

            company_name = (
                details.get("company")
                or details.get("company_name")
                or listing.get("company")
                or ""
            )
            title = (
                details.get("title")
                or details.get("job_title")
                or listing.get("title")
                or "Role"
            )
            job_url = details.get("job_url") or listing.get("job_url") or listing.get("url") or ""
            location = details.get("location") or listing.get("location") or country or ""

            # Prefer full description; fallback to minimal-but-nonempty signal
            desc = (
                details.get("description")
                or listing.get("description")
                or listing.get("snippet")
                or ""
            ).strip()
            if not desc:
                desc = " ".join(part for part in [title, company_name, location] if part)

            job_for_scoring: Dict[str, Any] = {
                "title": title,
                "company": company_name,
                "location": location,
                "description": desc,
                "job_url": job_url,
                "id": details.get("job_id") or details.get("id") or listing.get("id"),
            }

            logger.debug("Scoring input — title='%s' len(desc)=%d url=%s", title, len(desc), job_url)

            s = await score_match(cv, job_for_scoring)
            score = float(s.get("score", 0.0))
            logger.info("Scored: %s @ %s -> %.2f", title, company_name, score)

            # keep full vacancy text in the report rows
            scored_rows.append({
                "Job Post Title": title,
                "Company": company_name,
                "Compatibility Score": score,
                "job_id": job_for_scoring.get("id"),
                "job_url": job_url,
                "location": location,
                "Description": desc,
            })

            if score >= THRESHOLD:
                shortlisted.append({"job": job_for_scoring, "company": {}, "score": s})

        # Fallback: if none passed threshold, take top-N by score so we still generate artifacts
        if not shortlisted and scored_rows:
            logger.warning(
                "No jobs reached threshold %.2f. Falling back to top-%d by score.",
                THRESHOLD, MAX_DOCS,
            )
            top_rows = sorted(scored_rows, key=lambda r: r["Compatibility Score"], reverse=True)[:MAX_DOCS]
            shortlisted = []
            for r in top_rows:
                orig = next((j for j in jobs if (j.get("job_url") or j.get("url")) == r["job_url"]), {})
                job = {
                    "title": r["Job Post Title"],
                    "company": r["Company"],
                    "description": (orig.get("description") or orig.get("snippet") or r.get("Description") or ""),
                    "job_url": r["job_url"],
                    "id": r.get("job_id"),
                    "location": r.get("location", country or ""),
                }
                shortlisted.append({"job": job, "company": {}, "score": {"score": r["Compatibility Score"]}})
        else:
            shortlisted = shortlisted[:MAX_DOCS]

        # 3) GENERATE ARTIFACTS ———
        llm = make_client(SETTINGS.openai_model, temperature=0.2)
        files_created: List[str] = []
        ai_traces: List[Dict[str, Any]] = []

        for s in shortlisted:
            job = s["job"]
            job_title_fs = (job.get("title") or "Role").replace("/", "-").replace("\\", "-")
            company_name = job.get("company") or ""
            date = today_compact()

            logger.info("Generating CV + cover letter for: %s @ %s", job_title_fs, company_name)

            # --- CV
            ai_cv_logs: Dict[str, Any] = {}
            try:
                cv_user = (
                    f"CANDIDATE RAW CV:\n{cv.get('raw','')}\n\n"
                    f"TARGET JOB:\nTitle: {job.get('title','')}\nCompany: {company_name}\n"
                    f"Location: {job.get('location','')}\nDescription:\n{job.get('description','')}\n\n"
                    f"NOTES/KNOWLEDGE:\n{knowledge_snapshot()}"
                )
                cv_data = await _maybe_await(simple_json_chat, llm, SYSTEM_CV_UPDATE_JSON, cv_user)

                # Ensure header defaults if missing
                hdr = cv_data.setdefault("header", {})
                hdr.setdefault("name", cv.get("name", ""))
                hdr.setdefault("address", "")
                hdr.setdefault("phone", "")
                hdr.setdefault("email", "")
                hdr.setdefault("linkedin", "")

                # --- AI-Guard pass (optional; only if flags provided)
                if ai_target is not None or ai_max_iters is not None:
                    body_fields = [
                        "summary", "objective", "highlights",
                        "experience_text", "projects_text", "skills_text",
                        "plain_text", "education_text", "achievements_text",
                    ]
                    for field in body_fields:
                        if not cv_data.get(field):
                            continue
                        optimized, log = self._guard_reduce(
                            cv_data[field],
                            target=ai_target,
                            iters=ai_max_iters,
                            label=f"CV:{field}",
                        )
                        cv_data[field] = optimized
                        ai_cv_logs[field] = log

                cv_path = f"{ARTIFACTS_DIR}/cv_{job_title_fs}_{date}.pdf"
                render_cv_pdf(cv_path, job_title_fs, cv_data)
                files_created.append(cv_path)
            except Exception as e:
                logger.warning("CV generation failed for %s @ %s: %s", job_title_fs, company_name, e)

            # --- Cover Letter
            ai_cl_logs: Dict[str, Any] = {}
            try:
                cl_user = (
                    f"CANDIDATE CONTACTS (if present in CV text, reuse):\n{cv.get('raw','')[:1000]}"
                    f"\n\nJOB TARGET:\nTitle: {job.get('title','')}\nCompany: {company_name}\n"
                    f"Location: {job.get('location','')}\nDescription:\n{job.get('description','')}"
                )
                cl_data = await _maybe_await(simple_json_chat, llm, SYSTEM_COVER_LETTER_JSON, cl_user)

                rec = cl_data.setdefault("recipient", {})
                if company_name and not rec.get("company"):
                    rec["company"] = company_name

                # Collect intro/body/closing/ps (synthesize from plain_text if missing)
                parts = _collect_text_parts(cl_data)

                # --- AI-Guard optimization per part
                if ai_target is not None or ai_max_iters is not None:
                    for key, text in parts.items():
                        optimized, log = self._guard_reduce(
                            text, target=ai_target, iters=ai_max_iters, label=f"CL:{key}"
                        )
                        cl_data[key] = optimized
                        ai_cl_logs[key] = log

                    # If nothing present but plain_text exists, optimize whole
                    if not parts:
                        whole = (cl_data.get("plain_text") or "").strip()
                        if whole:
                            optimized, log = self._guard_reduce(
                                whole, target=ai_target, iters=ai_max_iters, label="CL:plain_text"
                            )
                            cl_data["plain_text"] = optimized
                            ai_cl_logs["plain_text"] = log

                # --- Normalize the closing: keep valediction alone, move run-on into body
                if cl_data.get("closing"):
                    val, extra = _split_valediction_runon(cl_data["closing"])
                    cl_data["closing"] = val
                    if extra:
                        _append_to_body(cl_data, extra)

                cl_path = f"{ARTIFACTS_DIR}/coverletter_{job_title_fs}_{date}.pdf"
                render_cover_letter_pdf(cl_path, job_title_fs, cl_data)
                files_created.append(cl_path)
            except Exception as e:
                logger.warning("Cover letter generation failed for %s @ %s: %s", job_title_fs, company_name, e)

            # Attach AI-Guard traces for this job (may be empty if flags not set)
            s["ai_guard"] = {"cv": ai_cv_logs, "cover_letter": ai_cl_logs}
            ai_traces.append({
                "job_url": job.get("job_url"),
                "title": job.get("title"),
                "company": job.get("company"),
                "ai_guard": s["ai_guard"],
            })

        # 4) MEMORY / REPORT ———
        add_outcome(
            session_id=session_id,
            topic=f"{role} {function} {country}".strip(),
            description=f"QuickAndReady completed. {len(shortlisted)} shortlisted / {num_results} results.",
            files=files_created,
        )

        logger.info(
            "QuickAndReady summary — scored: %d, shortlisted: %d, generated files: %d",
            len(scored_rows), len(shortlisted), len(files_created),
        )

        return {
            "session_id": session_id,
            "search_term": f"{role} {function} {country}".strip(),
            "number_of_results": num_results,
            "number_of_compatible_results": len(shortlisted),
            "number_of_outputs_generated": len(files_created),
            "all_results": scored_rows,    # includes full descriptions ("Description")
            "ai_guard_traces": ai_traces,  # per-job optimization logs
            "status": "ok",
        }
