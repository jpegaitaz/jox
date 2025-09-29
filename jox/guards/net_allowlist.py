from __future__ import annotations

ALLOWED_HOSTS = {
    "www.linkedin.com",
    "linkedin.com",
    "www.linkedin.cn",
}

def is_allowed(host: str) -> bool:
    host = (host or "").lower()
    return any(host == h or host.endswith("." + h) for h in ALLOWED_HOSTS)
