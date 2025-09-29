# jox/mcp/tool_adapters.py
from __future__ import annotations
from typing import Dict, Any, List
import logging

# Use our hardened driver + auth path from the vendored server
from jox.mcp.servers.linkedin_mcp_server.error_handler import safe_get_driver

logger = logging.getLogger(__name__)

class LinkedInTools:
    """
    Direct adapters (no MCP client): use our vendored driver manager + linkedin_scraper.
    This keeps everything local and avoids FastMCP client API differences.
    """

    def __init__(self) -> None:
        # Defer heavy imports until actually used to speed up CLI launch
        pass

    async def get_person_profile(self, username: str) -> Dict[str, Any]:
        from linkedin_scraper import Person  # type: ignore

        driver = safe_get_driver()
        url = f"https://www.linkedin.com/in/{username}/"
        logger.info("Scraping person profile: %s", url)
        person = Person(url, driver=driver, close_on_complete=False)

        experiences = [
            {
                "position_title": exp.position_title,
                "company": exp.institution_name,
                "from_date": exp.from_date,
                "to_date": exp.to_date,
                "duration": exp.duration,
                "location": exp.location,
                "description": exp.description,
            }
            for exp in person.experiences
        ]
        educations = [
            {
                "institution": edu.institution_name,
                "degree": edu.degree,
                "from_date": edu.from_date,
                "to_date": edu.to_date,
                "description": edu.description,
            }
            for edu in person.educations
        ]
        interests = [i.title for i in person.interests]
        accomplishments = [{"category": a.category, "title": a.title} for a in person.accomplishments]
        contacts = [{"name": c.name, "occupation": c.occupation, "url": c.url} for c in person.contacts]

        return {
            "name": person.name,
            "about": person.about,
            "experiences": experiences,
            "educations": educations,
            "interests": interests,
            "accomplishments": accomplishments,
            "contacts": contacts,
            "company": person.company,
            "job_title": person.job_title,
            "open_to_work": getattr(person, "open_to_work", False),
        }

    async def get_company_profile(self, company_name: str, get_employees: bool = False) -> Dict[str, Any]:
        from linkedin_scraper import Company  # type: ignore

        driver = safe_get_driver()
        url = f"https://www.linkedin.com/company/{company_name}/"
        logger.info("Scraping company: %s (employees=%s)", url, get_employees)
        company = Company(url, driver=driver, get_employees=get_employees, close_on_complete=False)

        showcase_pages = [
            {"name": p.name, "linkedin_url": p.linkedin_url, "followers": p.followers}
            for p in company.showcase_pages
        ]
        affiliated = [
            {"name": a.name, "linkedin_url": a.linkedin_url, "followers": a.followers}
            for a in company.affiliated_companies
        ]

        result: Dict[str, Any] = {
            "name": company.name,
            "about_us": company.about_us,
            "website": company.website,
            "phone": company.phone,
            "headquarters": company.headquarters,
            "founded": company.founded,
            "industry": company.industry,
            "company_type": company.company_type,
            "company_size": company.company_size,
            "specialties": company.specialties,
            "showcase_pages": showcase_pages,
            "affiliated_companies": affiliated,
            "headcount": company.headcount,
        }
        if get_employees and company.employees:
            result["employees"] = company.employees
        return result

    async def get_job_details(self, job_id: str) -> Dict[str, Any]:
        from linkedin_scraper import Job  # type: ignore

        driver = safe_get_driver()
        url = f"https://www.linkedin.com/jobs/view/{job_id}/"
        logger.info("Scraping job: %s", url)
        job = Job(url, driver=driver, close_on_complete=False)
        return job.to_dict()

    async def search_jobs(self, search_term: str) -> List[Dict[str, Any]]:
        from linkedin_scraper import JobSearch  # type: ignore

        driver = safe_get_driver()
        logger.info("Searching jobs: %s", search_term)
        js = JobSearch(driver=driver, close_on_complete=False, scrape=False)
        jobs = js.search(search_term)
        return [j.to_dict() for j in jobs]

    async def get_recommended_jobs(self) -> List[Dict[str, Any]]:
        from linkedin_scraper import JobSearch  # type: ignore

        driver = safe_get_driver()
        logger.info("Getting recommended jobs")
        js = JobSearch(driver=driver, close_on_complete=False, scrape=True, scrape_recommended_jobs=True)
        return [j.to_dict() for j in getattr(js, "recommended_jobs", []) or []]
