# SPDX-License-Identifier: Apache-2.0
"""
Indeed MCP (local) tools — HTTP (requests + BeautifulSoup), gentle rate-limited.

Tools:
- search_jobs(query, location, days=7, limit=20)
- get_job_details(job_key)

We keep it local (no FastMCP stdio client) to keep JOX simple.
"""
__all__ = ["search_jobs", "get_job_details"]
from .tools import search_jobs, get_job_details

