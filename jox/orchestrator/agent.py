# jox/orchestrator/agent.py
from __future__ import annotations

import os
import asyncio
import logging
import uuid
from typing import Dict, Any, List

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


class Orchestrator:
    """
    Coordinates search → score → shortlist → generate artifacts.
    Job source is taken from SETTINGS.job_source or JOB_SOURCE env:
      - "indeed" (default)
      - "jobup" (if wired via get_job_tools)
    """

    def __init__(self) -> None:
        source = getattr(SETTINGS, "job_source", None) or os.getenv("JOB_SOURCE", "indeed")
        self.jobs = get_job_tools(source)

    async def _fetch_details_best_effort(self, listing: Dict[str, Any]) -> Dict[str, Any]:
        """
        If the adapter exposes get_job_details, use it to enrich the listing.
        Always return at least title/company/job_url when possible.
        """
        job_id_or_url = listing.get("job_url") or listing.get("url") or listing.get("id") or ""
        if not job_id_or_url:
            return listing

        if hasattr(self.jobs, "get_job_details"):
            try:
                details = await self.jobs.get_job_details(job_id_or_url)
                # Ensure minimum fields exist
                details.setdefault("title", listing.get("title"))
                details.setdefault("company", listing.get("company"))
                details.setdefault("location", listing.get("location"))
                details.setdefault("job_url", listing.get("job_url") or listing.get("url"))
                return details
            except Exception as e:
                logger.debug("get_job_details failed (%s); using listing only.", e)

        return listing

    async def quick_and_ready(self, cv: Dict[str, Any], function: str, role: str, country: str) -> Dict[str, Any]:
        # Ensure artifacts directory exists
        os.makedirs(ARTIFACTS_DIR, exist_ok=True)

        session_id = str(uuid.uuid4())
        search_term = f"{role} {function}".strip()

        # --- 1) Search
        logger.info("Starting QuickAndReady: query='%s' location='%s'", search_term, country)
        jobs = await self.jobs.search_jobs(
            search_term=search_term,
            location=country,
            days=7,          # adapters that don't use 'days' should ignore it
            limit=30,
            country=country, # some adapters use this to pick domain/locale
        )
        num_results = len(jobs)
        logger.info("Search returned %d listings", num_results)

        # --- 2) Score + shortlist
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
            job_url = details.get("job_url") or listing.get("job_url") or listing.get("url")
            location = details.get("location") or listing.get("location") or ""

            # Prefer full description; fallback to minimal-but-nonempty signal
            desc = (
                details.get("description")
                or listing.get("description")
                or listing.get("snippet")
                or ""
            ).strip()
            if not desc:
                # absolute minimum signal so heuristics/LLM don't collapse to 0
                desc = " ".join(filter(None, [title, company_name, location]))

            job_for_scoring: Dict[str, Any] = {
                "title": title,
                "company": company_name,
                "location": location,
                "description": desc,
                "job_url": job_url,
                "id": details.get("job_id") or details.get("id") or listing.get("id"),
            }

            logger.debug(
                "Scoring input — title='%s' len(desc)=%d url=%s",
                title, len(desc or ""), job_url,
            )

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

        # Fallback: if none passed threshold, take top-N by score
        if not shortlisted and scored_rows:
            logger.warning(
                "No jobs reached threshold %.2f. Falling back to top-%d by score.",
                THRESHOLD, MAX_DOCS,
            )
            top_rows = sorted(scored_rows, key=lambda r: r["Compatibility Score"], reverse=True)[:MAX_DOCS]
            shortlist: List[Dict[str, Any]] = []
            for r in top_rows:
                orig = next((j for j in jobs if (j.get("job_url") or j.get("url")) == r["job_url"]), {})
                job = {
                    "title": r["Job Post Title"],
                    "company": r["Company"],
                    "description": (orig.get("description") or orig.get("snippet") or ""),
                    "job_url": r["job_url"],
                    "id": r.get("job_id"),
                    "location": orig.get("location", ""),
                }
                shortlist.append({"job": job, "company": {}, "score": {"score": r["Compatibility Score"]}})
            shortlisted = shortlist
        else:
            shortlisted = shortlisted[:MAX_DOCS]

        # --- 3) Generate artifacts (JSON → PDF)
        llm = make_client(SETTINGS.openai_model, temperature=0.2)
        files_created: List[str] = []

        for s in shortlisted:
            job = s["job"]
            job_title_fs = (job.get("title") or "Role").replace("/", "-").replace("\\", "-")
            company_name = job.get("company") or ""
            date = today_compact()

            logger.info("Generating CV + cover letter for: %s @ %s", job_title_fs, company_name)

            # CV
            try:
                cv_user = (
                    f"CANDIDATE RAW CV:\n{cv.get('raw','')}\n\n"
                    f"TARGET JOB:\nTitle: {job.get('title','')}\nCompany: {company_name}\n"
                    f"Location: {job.get('location','')}\nDescription:\n{job.get('description','')}\n\n"
                    f"NOTES/KNOWLEDGE:\n{knowledge_snapshot()}"
                )
                cv_data = await simple_json_chat(llm, SYSTEM_CV_UPDATE_JSON, cv_user)

                hdr = cv_data.setdefault("header", {})
                hdr.setdefault("name", cv.get("name", ""))
                hdr.setdefault("address", "")
                hdr.setdefault("phone", "")
                hdr.setdefault("email", "")
                hdr.setdefault("linkedin", "")

                cv_path = f"{ARTIFACTS_DIR}/cv_{job_title_fs}_{date}.pdf"
                render_cv_pdf(cv_path, job_title_fs, cv_data)
                files_created.append(cv_path)
            except Exception as e:
                logger.warning("CV generation failed for %s @ %s: %s", job_title_fs, company_name, e)

            # Cover letter
            try:
                cl_user = (
                    f"CANDIDATE CONTACTS (if present in CV text, reuse):\n{cv.get('raw','')[:1000]}"
                    f"\n\nJOB TARGET:\nTitle: {job.get('title','')}\nCompany: {company_name}\n"
                    f"Location: {job.get('location','')}\nDescription:\n{job.get('description','')}"
                )
                cl_data = await simple_json_chat(llm, SYSTEM_COVER_LETTER_JSON, cl_user)

                rec = cl_data.setdefault("recipient", {})
                if company_name and not rec.get("company"):
                    rec["company"] = company_name

                cl_path = f"{ARTIFACTS_DIR}/coverletter_{job_title_fs}_{date}.pdf"
                render_cover_letter_pdf(cl_path, job_title_fs, cl_data)
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
            len(scored_rows), len(shortlisted), len(files_created),
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
