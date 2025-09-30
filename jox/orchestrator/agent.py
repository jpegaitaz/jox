from __future__ import annotations

import os
import asyncio
import logging
import uuid
from typing import Dict, Any, List, Optional

from jox.orchestrator.scoring import score_match
from jox.orchestrator.memory import knowledge_snapshot, add_outcome
from jox.cv.render import render_cv_pdf, render_cover_letter_pdf
from jox.llm.openai_client import make_client
from jox.llm.prompts import SYSTEM_COVER_LETTER, SYSTEM_CV_UPDATE
from jox.settings import SETTINGS
from jox.utils.dates import today_compact
from jox.mcp.tool_adapters import IndeedTools

logger = logging.getLogger(__name__)

ARTIFACTS_DIR = "outputs/artifacts"


class Orchestrator:
    def __init__(self) -> None:
        # Indeed-only (we’re leaving LinkedIn aside for now)
        self.jobs = IndeedTools()

    async def _fetch_indeed_details(self, listing: Dict[str, Any]) -> Dict[str, Any]:
        """
        Best-effort enrichment for an Indeed listing.
        If get_job_details is implemented server-side, use it; otherwise fall back to the listing.
        """
        job_id_or_url = listing.get("job_url") or listing.get("url") or listing.get("id") or ""
        if not job_id_or_url:
            return listing

        # Try the details endpoint if wired
        if hasattr(self.jobs, "get_job_details"):
            try:
                details = await self.jobs.get_job_details(job_id_or_url)
                # ensure minimum fields are present
                details.setdefault("title", listing.get("title"))
                details.setdefault("company", listing.get("company"))
                details.setdefault("job_url", listing.get("job_url") or listing.get("url"))
                return details
            except Exception as e:
                logger.debug("get_job_details failed (%s); using listing only.", e)

        return listing

    async def quick_and_ready(self, cv: Dict[str, Any], function: str, role: str, country: str) -> Dict[str, Any]:
        # Ensure artifacts directory exists
        os.makedirs(ARTIFACTS_DIR, exist_ok=True)

        session_id = str(uuid.uuid4())
        # Keep query compact & predictable for Indeed
        # We search without the country in the keywords (Indeed has a separate location param)
        search_term = f"{role} {function}".strip()

        # --- 1) Search (short horizon; keep it humane)
        logger.info("Starting QuickAndReady: query='%s' location='%s'", search_term, country)
        jobs = await self.jobs.search_jobs(
            search_term=search_term,
            location=country,
            days=7,
            limit=10,
            country=country,  # also controls indeed.* domain
        )
        num_results = len(jobs)
        logger.info("Indeed returned %d listings", num_results)

        # --- 2) Score + shortlist
        THRESHOLD: float = float(getattr(SETTINGS, "compatibility_threshold", 7.5))
        MAX_DOCS: int = int(getattr(SETTINGS, "max_docs", 5))

        shortlisted: List[Dict[str, Any]] = []
        scored_rows: List[Dict[str, Any]] = []

        # Only look at the top ~30 from search (tunable)
        for listing in jobs[:30]:
            details = await self._fetch_indeed_details(listing)

            company_name = (
                details.get("company")
                or details.get("company_name")
                or listing.get("company")
                or ""
            )
            title = details.get("title") or details.get("job_title") or listing.get("title") or "Role"
            job_url = details.get("job_url") or listing.get("job_url") or listing.get("url")

            # Build a lean “job” context for scoring
            job_for_scoring: Dict[str, Any] = {
                "title": title,
                "company": company_name,
                "location": details.get("location") or listing.get("location"),
                "description": details.get("description") or listing.get("description") or listing.get("snippet") or "",
                "job_url": job_url,
                "id": details.get("job_id") or details.get("id") or listing.get("id"),
            }

            s = await score_match(cv, job_for_scoring)
            score = float(s.get("score", 0.0))
            logger.info("Scored: %s @ %s -> %.2f", title, company_name, score)

            scored_rows.append(
                {
                    "Job Post Title": title,
                    "Company": company_name,
                    "Compatibility Score": score,
                    "job_id": job_for_scoring.get("id"),
                    "job_url": job_url,
                }
            )

            if score >= THRESHOLD:
                shortlisted.append({"job": job_for_scoring, "company": {}, "score": s})

        # Fallback: if none passed threshold, take top-N by score so we still generate artifacts
        if not shortlisted and scored_rows:
            logger.warning(
                "No jobs reached threshold %.2f. Falling back to top-%d by score.",
                THRESHOLD,
                MAX_DOCS,
            )
            top_rows = sorted(scored_rows, key=lambda r: r["Compatibility Score"], reverse=True)[:MAX_DOCS]
            # Re-hydrate job dicts for generation; we can re-fetch details if needed.
            shortlisted = []
            for r in top_rows:
                # Try to find the original listing to pull description/snippet
                orig = next((j for j in jobs if (j.get("job_url") or j.get("url")) == r["job_url"]), {})
                job = {
                    "title": r["Job Post Title"],
                    "company": r["Company"],
                    "description": (orig.get("description") or orig.get("snippet") or ""),
                    "job_url": r["job_url"],
                    "id": r.get("job_id"),
                }
                shortlisted.append({"job": job, "company": {}, "score": {"score": r["Compatibility Score"]}})
        else:
            shortlisted = shortlisted[:MAX_DOCS]

        # --- 3) Generate artifacts for shortlisted
        # Sturdier client (timeout) + helper for content extraction across client variants
        llm = make_client(SETTINGS.openai_model, temperature=0.2)

        def _msg_content(resp: Any) -> str:
            # LangChain ChatResult (or AIMessage)
            if hasattr(resp, "content"):
                return resp.content
            # OpenAI python client shape
            try:
                return resp.choices[0].message.content
            except Exception:
                return str(resp)

        files_created: List[str] = []

        for s in shortlisted:
            job = s["job"]
            job_title_fs = (job.get("title") or "Role").replace("/", "-")
            company_name = job.get("company") or ""
            date = today_compact()

            logger.info("Generating CV + cover letter for: %s @ %s", job_title_fs, company_name)

            # CV draft
            try:
                from langchain.schema import SystemMessage, HumanMessage  # local import to avoid startup cost
                cv_user = (
                    f"TARGET JOB:\n{job.get('description','')}\n\n"
                    f"ORIGINAL CV:\n{cv.get('raw','')}\n\n"
                    f"ENTRIES & OUTCOMES:\n{knowledge_snapshot()}"
                )
                cv_resp = await asyncio.wait_for(
                    llm.ainvoke([SystemMessage(content=SYSTEM_CV_UPDATE), HumanMessage(content=cv_user)]),
                    timeout=120,
                )
                cv_text = _msg_content(cv_resp)
                cv_path = f"{ARTIFACTS_DIR}/cv_{job_title_fs}_{date}.pdf"
                render_cv_pdf(cv_path, job_title_fs, cv_text)
                files_created.append(cv_path)
            except Exception as e:
                logger.warning("CV generation failed for %s @ %s: %s", job_title_fs, company_name, e)

            # Cover letter
            try:
                from langchain.schema import SystemMessage, HumanMessage  # local import again
                cl_user = (
                    f"JOB [{job_title_fs} @ {company_name}]:\n{job.get('description','')}\n\n"
                    f"CANDIDATE:\n{cv.get('raw','')}"
                )
                cl_resp = await asyncio.wait_for(
                    llm.ainvoke([SystemMessage(content=SYSTEM_COVER_LETTER), HumanMessage(content=cl_user)]),
                    timeout=120,
                )
                cl_text = _msg_content(cl_resp)
                cl_path = f"{ARTIFACTS_DIR}/coverletter_{job_title_fs}_{date}.pdf"
                render_cover_letter_pdf(cl_path, job_title_fs, cl_text)
                files_created.append(cl_path)
            except Exception as e:
                logger.warning("Cover letter generation failed for %s @ %s: %s", job_title_fs, company_name, e)

        # --- 4) Outcome memory
        add_outcome(
            session_id=session_id,
            topic=f"{role} {function} {country}".strip(),
            description=f"QuickAndReady completed. {len(shortlisted)} shortlisted / {num_results} results.",
            files=files_created,
        )

        logger.info(
            "QuickAndReady summary — scored: %d, shortlisted: %d, generated files: %d",
            len(scored_rows),
            len(shortlisted),
            len(files_created),
        )

        return {
            "session_id": session_id,
            "search_term": f"{role} {function} {country}".strip(),
            "number_of_results": num_results,
            "number_of_compatible_results": len(shortlisted),
            "number_of_outputs_generated": len(files_created),
            "all_results": scored_rows,
            "status": "ok",
        }
