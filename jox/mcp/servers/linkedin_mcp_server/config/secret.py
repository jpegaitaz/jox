# Minimal env-only secrets accessor for JOX

import os

class Secrets:
    """Env-only cookie accessor. No keyring, no prompts, no logging."""

    @staticmethod
    def get_cookie() -> str:
        """
        Returns the LinkedIn session cookie in 'li_at=...' format.
        Raises RuntimeError if missing or malformed.
        """
        raw = (os.getenv("LINKEDIN_COOKIE") or "").strip()
        if not raw:
            raise RuntimeError("LINKEDIN_COOKIE not set. Expected 'li_at=...'.")
        # accept either raw token or 'li_at=...'
        cookie = raw if raw.lower().startswith("li_at=") else f"li_at={raw}"
        if len(cookie) <= len("li_at="):
            raise RuntimeError("LINKEDIN_COOKIE looks malformed. Expected 'li_at=...'.")
        return cookie
