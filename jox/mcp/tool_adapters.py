# jox/mcp/tool_adapters.py
from __future__ import annotations
from typing import Dict, Any, List, Callable, TypeVar, Optional
import logging
import time

# LinkedIn helpers still rely on the hardened Selenium driver
from jox.mcp.servers.linkedin_mcp_server.error_handler import safe_get_driver

# Optional: only used for targeted exception handling
try:
    from selenium.common.exceptions import TimeoutException, WebDriverException  # type: ignore
except Exception:  # pragma: no cover
    TimeoutException = WebDriverException = Exception  # type: ignore

logger = logging.getLogger(__name__)
T = TypeVar("T")


def _with_retries(
    fn: Callable[[], T],
    *,
    attempts: int = 2,
    backoff_sec: float = 2.0,
    recover: Callable[[], None] | None = None,
    context: str = "operation",
) -> T:
    """
    Run `fn` with a few retries. If provided, `recover()` runs before each retry.
    Raises the last exception if all attempts fail.
    """
    last_err: Exception | None = None
    for i in range(1, attempts + 1):
        try:
            return fn()
        except TimeoutException as e:  # type: ignore
            last_err = e
            logger.warning("%s timed out (attempt %d/%d).", context, i, attempts)
        except WebDriverException as e:  # type: ignore
            last_err = e
            logger.warning("%s webdriver error (attempt %d/%d): %s", context, i, attempts, e)
        except Exception as e:
            last_err = e
            logger.warning("%s failed (attempt %d/%d): %s", context, i, attempts, e)

        if i < attempts:
            if recover:
                try:
                    recover()
                except Exception as rec_e:  # best-effort
                    logger.debug("Recover hook failed: %s", rec_e)
            time.sleep(backoff_sec)

    assert last_err is not None
    raise last_err


class IndeedTools:
    def __init__(self) -> None:
        from jox.mcp.servers.indeed_mcp_server import search_jobs as _s, get_job_details as _d
        self._search = _s
        self._details = _d

    async def search_jobs(
        self,
        search_term: str,
        location: str = "",
        days: int = 7,
        limit: int = 20,
        *,
        country: Optional[str] = None,
    ):
        import asyncio
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None,
            lambda: self._search(
                query=search_term,
                location=location,
                days=days,
                limit=limit,
                country=country,
            ),
        )

    async def get_job_details(self, job_id_or_url: str) -> Dict[str, Any]:
        import asyncio
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, lambda: self._details(job_id_or_url))


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

        def _do() -> Person:
            return Person(url, driver=driver, close_on_complete=False)

        person = _with_retries(
            _do,
            attempts=2,
            context="person profile scrape",
            recover=lambda: driver.refresh(),
        )

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

        def _do() -> Company:
            return Company(url, driver=driver, get_employees=get_employees, close_on_complete=False)

        company = _with_retries(
            _do,
            attempts=2,
            context="company profile scrape",
            recover=lambda: driver.refresh(),
        )

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

        def _do() -> Dict[str, Any]:
            job = Job(url, driver=driver, close_on_complete=False)
            return job.to_dict()

        return _with_retries(
            _do,
            attempts=2,
            context="job details scrape",
            recover=lambda: driver.refresh(),
        )

    async def search_jobs(self, search_term: str) -> List[Dict[str, Any]]:
        """
        Primary: linkedin_scraper.JobSearch (fast path).
        Fallback: open Jobs search URL, handle consent, scroll & harvest /jobs/view/ links.
        """
        from urllib.parse import quote_plus
        import time as _time
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC  # noqa: F401  (kept for future use)
        from selenium.common.exceptions import TimeoutException, NoSuchElementException
        from linkedin_scraper import JobSearch  # type: ignore

        driver = safe_get_driver()
        logger.info("Searching jobs: %s", search_term)

        # 1) Library path (single attempt)
        try:
            js = JobSearch(driver=driver, close_on_complete=False, scrape=False)
            jobs = js.search(search_term)
            return [j.to_dict() for j in jobs]
        except TimeoutException:
            logger.warning("job search timed out in library path; using URL fallback.")

        # 2) URL fallback
        tokens = search_term.split()
        location = tokens[-1] if len(tokens) > 1 else ""
        keywords = " ".join(tokens[:-1]) or search_term

        url = (
            "https://www.linkedin.com/jobs/search/"
            f"?keywords={quote_plus(keywords)}"
            f"&location={quote_plus(location)}"
            f"&f_TPR=r604800&position=1&pageNum=0"
        )
        logger.info("Fallback jobs URL: %s", url)
        driver.get(url)

        wait = WebDriverWait(driver, 120)

        def _dismiss_cookie_banner():
            candidates = [
                ("css selector", "button[action-type='ACCEPT']"),
                ("css selector", "button[aria-label*='Accept']"),
                ("xpath", "//button[contains(., 'Accept') or contains(., 'accept')]"),
                ("css selector", "button[data-control-name='ga-cookie-consent-accept-all']"),
            ]
            for by, sel in candidates:
                try:
                    from selenium.webdriver.common.by import By as _By
                    btn = driver.find_element(getattr(_By, by.replace(" ", "_").upper()), sel)
                    if btn.is_displayed():
                        btn.click()
                        logger.info("Dismissed cookie banner via selector: %s", sel)
                        _time.sleep(1)
                        return
                except NoSuchElementException:
                    continue
                except Exception:
                    continue

        _dismiss_cookie_banner()

        container_selectors = [
            "ul.scaffold-layout__list-container",
            "div.jobs-search-results-list",
            "[data-search-results-container='true']",
            "div.jobs-search__results-list",
        ]

        def _any_results_present(driver):
            from selenium.webdriver.common.by import By as _By
            for sel in container_selectors:
                if driver.find_elements(_By.CSS_SELECTOR, sel):
                    return True
            links = driver.find_elements(_By.CSS_SELECTOR, "a[href*='/jobs/view/']")
            return len(links) > 0

        try:
            wait.until(_any_results_present)
            logger.info("Initial results signal detected (container or job links).")
        except TimeoutException:
            logger.warning("No results signal yet—continuing with scroll harvesting.")

        driver.execute_script("window.scrollTo(0, 0);")
        _time.sleep(0.8)

        results: List[Dict[str, Any]] = []
        seen = set()

        def _harvest_now() -> int:
            from selenium.webdriver.common.by import By as _By
            links = driver.find_elements(_By.CSS_SELECTOR, "a[href*='/jobs/view/']")
            added = 0
            for a in links:
                href = a.get_attribute("href") or ""
                if "/jobs/view/" not in href:
                    continue
                tail = href.split("/jobs/view/")[-1]
                jid = "".join(ch for ch in tail if ch.isdigit())
                if not jid or jid in seen:
                    continue
                seen.add(jid)
                title = (a.text or "").strip()
                results.append(
                    {"job_id": jid, "job_url": f"https://www.linkedin.com/jobs/view/{jid}/", "title": title}
                )
                added += 1
            return added

        start = _time.time()
        last_log = start
        while _time.time() - start < 20:
            _harvest_now()
            driver.execute_script("window.scrollBy(0, 800);")
            _time.sleep(0.6)
            driver.execute_script("window.scrollBy(0, 1200);")
            _time.sleep(0.6)
            driver.execute_script("window.scrollTo(0, 0);")
            _time.sleep(0.5)

            now = _time.time()
            if now - last_log > 5:
                logger.info("Harvest progress: %d job links collected so far", len(results))
                last_log = now

            if len(results) >= 20:
                break

        _harvest_now()
        logger.info("URL fallback collected %d jobs", len(results))
        return results

    async def get_recommended_jobs(self) -> List[Dict[str, Any]]:
        from linkedin_scraper import JobSearch  # type: ignore

        driver = safe_get_driver()
        logger.info("Getting recommended jobs")

        def _do() -> List[Dict[str, Any]]:
            js = JobSearch(driver=driver, close_on_complete=False, scrape=True, scrape_recommended_jobs=True)
            recs = getattr(js, "recommended_jobs", None) or []
            return [j.to_dict() for j in recs]

        try:
            return _with_retries(
                _do,
                attempts=2,
                context="recommended jobs",
                recover=lambda: driver.refresh(),
            )
        except Exception as e:
            logger.warning("Recommended jobs failed after retries (%s). Returning empty list.", e)
            return []

