from __future__ import annotations
import os
from dataclasses import dataclass

@dataclass(frozen=True)
class Settings:
    log_level: str = os.getenv("JOX_LOG_LEVEL", "INFO")
    headless: bool = os.getenv("JOX_HEADLESS", "1") in ("1", "true", "True")
    log_json: bool = os.getenv("JOX_LOG_JSON", "0") in ("1", "true", "True")
    validate_cookie: bool = os.getenv("JOX_VALIDATE_COOKIE", "0") in ("1", "true", "True")

    linkedin_cookie: str = os.getenv("LINKEDIN_COOKIE", "")
    chromedriver: str | None = os.getenv("CHROMEDRIVER") or None

    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    openai_model: str = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

SETTINGS = Settings()
