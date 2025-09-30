# jox/scripts/get_li_at.py
# Usage: python jox/scripts/get_li_at.py
# Requires: pip install selenium webdriver-manager pyperclip

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import pyperclip  # type: ignore
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager


ENV_PATH = Path(__file__).resolve().parents[1] / ".env"  # -> jox/.env


def append_or_replace_env(key: str, value: str, env_path: Path = ENV_PATH) -> None:
    """Write LINKEDIN_COOKIE to .env (replace if exists)."""
    lines = []
    if env_path.exists():
        with env_path.open("r", encoding="utf-8") as f:
            lines = f.read().splitlines()

    # remove prior definitions
    lines = [ln for ln in lines if not ln.startswith(f"{key}=")]
    lines.append(f'{key}="{value}"')  # quote to protect special chars

    with env_path.open("w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def get_linkedin_li_at_cookie() -> str:
    # Visible browser is best for CAPTCHAs/2FA; comment out headless if you want GUI
    opts = Options()
    # opts.add_argument("--headless=new")  # keep commented for interactive login

    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=opts)
    try:
        driver.get("https://www.linkedin.com/login")
        print("👉 A Chrome window opened. Log in to LinkedIn there.")
        print("   Complete any CAPTCHA/2FA if prompted.")
        input("   Press ENTER here once you are on your feed (logged in). ")

        # Ensure cookies are set
        driver.get("https://www.linkedin.com/feed/")
        time.sleep(2)

        cookie = driver.get_cookie("li_at")
        if not cookie or not cookie.get("value"):
            raise RuntimeError("Could not find li_at cookie. Are you logged in?")

        li_at = cookie["value"]

        # Copy to clipboard (best effort)
        try:
            pyperclip.copy(li_at)
            print("✅ li_at copied to clipboard.")
        except Exception:
            pass

        # Masked print
        masked = li_at[:6] + "..." + li_at[-6:]
        print(f"li_at (masked): {masked}")

        return li_at
    finally:
        driver.quit()


def main() -> None:
    li_at = get_linkedin_li_at_cookie()

    # JOX expects LINKEDIN_COOKIE to be either "li_at=..." or just the value.
    # Most of your code reads just the raw value; we'll store raw:
    append_or_replace_env("LINKEDIN_COOKIE", li_at)
    print(f"📝 Wrote LINKEDIN_COOKIE to {ENV_PATH}")

    # Friendly shell export line
    print("\nIf you prefer exporting instead of .env, run:")
    print(f'  export LINKEDIN_COOKIE="{li_at}"')

    # Reminder
    print("\nℹ️ Restart your shell or `source jox/.env` before re-running JOX.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(1)
