from __future__ import annotations
from typing import Dict, Any, List
import uuid

from jox.mcp.tool_adapters import LinkedInTools
from jox.orchestrator.scoring import score_match
from jox.orchestrator.memory import knowledge_snapshot, add_outcome
from jox.cv.render import render_cv_pdf, render_cover_letter_pdf
from jox.llm.openai_client import make_client
from jox.llm.prompts import SYSTEM_COVER_LETTER, SYSTEM_CV_UPDATE
from jox.settings import SETTINGS
from jox.utils.dates import today_compact

ARTIFACTS_DIR = "outputs/artifacts"

class Orchestrator:
    def __init__(self):
        self.li = LinkedInTools()  # MCP-backed

    async def quick_and_ready(self, cv: Dict[str, Any], function: str, role: str, country: str) -> Dict[str, Any]:
        session_id = str(uuid.uuid4())
        search_term = f"{role} {function} {country}".strip()
        jobs = await self.li.search_jobs(search_term)
        num_results = len(jobs)

        shortlisted: List[Dict[str, Any]] = []
        scored_rows: List[Dict[str, Any]] = []
        for j in jobs[:30]:
            details = await self.li.get_job_details(j.get("job_id") or j.get("id") or j.get("job_url") or "")
            company = {}
            company_name = details.get("company") or details.get("company_name")
            if company_name:
                company = await self.li.get_company_profile(company_name, get_employees=False)
            s = await score_match(cv, {**details, **({"company": company_name} if company_name else {})})
            scored_rows.append({
                "Job Post Title": details.get("title") or details.get("job_title"),
                "Company": company_name,
                "Compatibility Score": s["score"],
                "job_id": details.get("job_id") or details.get("id"),
                "job_url": details.get("job_url"),
            })
            if s["score"] >= 8.0:
                shortlisted.append({"job": details, "company": company, "score": s})

        # Generate artifacts for shortlisted
        llm = make_client(SETTINGS.openai_model, temperature=0.2)
        files_created: List[str] = []
        for s in shortlisted:
            job = s["job"]
            job_title = (job.get("title") or job.get("job_title") or "Role").replace("/", "-")
            date = today_compact()
            # Draft updated CV text
            from langchain.schema import SystemMessage, HumanMessage
            cv_user = f"TARGET JOB:\n{job.get('description','')}\n\nORIGINAL CV:\n{cv.get('raw','')}\n\nENTRIES & OUTCOMES:\n{knowledge_snapshot()}"
            cv_resp = await llm.ainvoke([SystemMessage(content=SYSTEM_CV_UPDATE), HumanMessage(content=cv_user)])
            cv_path = f"{ARTIFACTS_DIR}/cv_{job_title}_{date}.pdf"
            render_cv_pdf(cv_path, job_title, cv_resp.content)
            files_created.append(cv_path)

            # Cover letter
            cl_user = f"JOB [{job_title} @ {job.get('company','')}]:\n{job.get('description','')}\n\nCANDIDATE:\n{cv.get('raw','')}"
            cl_resp = await llm.ainvoke([SystemMessage(content=SYSTEM_COVER_LETTER), HumanMessage(content=cl_user)])
            cl_path = f"{ARTIFACTS_DIR}/coverletter_{job_title}_{date}.pdf"
            render_cover_letter_pdf(cl_path, job_title, cl_resp.content)
            files_created.append(cl_path)

        # Outcome memory
        add_outcome(
            session_id=session_id,
            topic=search_term,
            description=f"QuickAndReady completed. {len(shortlisted)} shortlisted / {num_results} results.",
            files=files_created,
        )

        return {
            "session_id": session_id,
            "search_term": search_term,
            "number_of_results": num_results,
            "number_of_compatible_results": len(shortlisted),
            "number_of_outputs_generated": len(files_created),
            "all_results": scored_rows,
            "status": "ok",
        }
