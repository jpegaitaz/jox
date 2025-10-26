from __future__ import annotations

import os
from dataclasses import dataclass, field

from dotenv import load_dotenv
load_dotenv()  # load .env early


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, "").strip() or default)
    except Exception:
        return default


def _env_int(name: str, default: int) -> int:
    try:
        return int((os.getenv(name, "") or str(default)).strip())
    except Exception:
        return default


def _env_bool(name: str, default: bool) -> bool:
    v = os.getenv(name)
    if v is None:
        return default
    v = v.strip().lower()
    return v in {"1", "true", "yes", "on", "y", "t"}


@dataclass
class _Settings:
    # LLM model
    openai_model: str = field(default_factory=lambda: os.getenv("OPENAI_MODEL", "gpt-4o-mini"))

    # Shortlist knobs
    compatibility_threshold: float = field(
        default_factory=lambda: _env_float("COMPATIBILITY_THRESHOLD", 7.5)
    )
    max_docs: int = field(default_factory=lambda: _env_int("MAX_DOCS", 5))

    # Logging
    log_level: str = field(default_factory=lambda: os.getenv("LOG_LEVEL", "INFO").upper())
    log_json: bool = field(default_factory=lambda: _env_bool("LOG_JSON", False))  # <-- restored


SETTINGS = _Settings()
