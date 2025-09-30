# jox/mcp/servers/indeed_mcp_server/config/settings.py
from __future__ import annotations
import os
from dataclasses import dataclass, field

def _env(name: str, default: str) -> str:
    v = os.getenv(name)
    return v if v else default

@dataclass
class _HTTP:
    timeout_s: float = float(_env("INDEED_TIMEOUT_S", "20"))
    min_sleep_s: float = float(_env("INDEED_MIN_SLEEP_S", "1.0"))
    max_sleep_s: float = float(_env("INDEED_MAX_SLEEP_S", "2.2"))
    retries: int = int(_env("INDEED_RETRIES", "3"))
    user_agent: str = _env(
        "INDEED_UA",
        # A modern Chrome UA (arm64 Mac). Override via env if you like.
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0.0.0 Safari/537.36"
    )
    accept_language: str = _env("INDEED_ACCEPT_LANGUAGE", "en-US,en;q=0.9")
    use_selenium_fallback: bool = _env("INDEED_USE_SELENIUM_FALLBACK", "1") in {"1", "true", "True"}
    max_pages: int = int(_env("INDEED_MAX_PAGES", "2"))

COUNTRY_TLD = {
    # minimal map; extend as needed
    "switzerland": "ch.indeed.com",
    "france": "fr.indeed.com",
    "germany": "de.indeed.com",
    "spain": "es.indeed.com",
    "italy": "it.indeed.com",
    "united kingdom": "uk.indeed.com",
    "united states": "www.indeed.com",
}

@dataclass
class _Settings:
    http: _HTTP = field(default_factory=_HTTP)
    max_pages: int = field(default_factory=lambda: int(os.getenv("INDEED_MAX_PAGES", "2")))

SETTINGS = _Settings()
