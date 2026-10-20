"""Universal session manager with cookie-based persistence.

Handles login sessions for any platform that requires authentication.
First run opens a visible browser for manual login + 2FA; subsequent runs
load saved cookies and run headless.
"""

from __future__ import annotations

import json
import os
import random
import time
from pathlib import Path
from typing import Any

from playwright.sync_api import sync_playwright, Browser, BrowserContext, Page


class CookieManager:
    """Manages per-domain cookie persistence for login sessions."""

    def __init__(self, cookies_dir: str = "state/cookies"):
        self.cookies_dir = Path(cookies_dir)
        self.cookies_dir.mkdir(parents=True, exist_ok=True)
        # Restrict directory permissions
        os.chmod(self.cookies_dir, 0o700)

    def _cookie_path(self, domain: str) -> Path:
        safe_name = domain.replace(".", "_").replace(":", "_")
        return self.cookies_dir / f"{safe_name}.json"

    def get_cookies(self, domain: str) -> list[dict] | None:
        """Load saved cookies for a domain. Returns None if not found."""
        path = self._cookie_path(domain)
        if not path.exists():
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            os.chmod(path, 0o600)
            return data if isinstance(data, list) else None
        except Exception:
            return None

    def save_cookies(self, domain: str, cookies: list[dict]) -> None:
        """Save cookies for a domain with restricted permissions."""
        path = self._cookie_path(domain)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(cookies, f, indent=2)
        os.chmod(path, 0o600)

    def clear_cookies(self, domain: str) -> None:
        """Delete saved cookies for a domain (forces re-login)."""
        path = self._cookie_path(domain)
        if path.exists():
            path.unlink()

    def list_domains(self) -> list[str]:
        """Return list of domains with saved cookies."""
        return [p.stem.replace("_", ".") for p in self.cookies_dir.glob("*.json")]


class BrowserLauncher:
    """Launches Playwright browsers with session cookie support."""

    def __init__(
        self,
        cookie_manager: CookieManager,
        headless_after_login: bool = True,
        login_timeout_seconds: int = 600,
        session_check_timeout_seconds: int = 10,
    ):
        self.cookie_manager = cookie_manager
        self.headless_after_login = headless_after_login
        self.login_timeout_seconds = login_timeout_seconds
        self.session_check_timeout_seconds = session_check_timeout_seconds
        self._playwright = None
        self._browser: Browser | None = None

    def _get_playwright(self):
        if self._playwright is None:
            self._playwright = sync_playwright().start()
        return self._playwright

    def launch(self, headless: bool = False) -> Browser:
        """Launch a Chromium browser instance."""
        pw = self._get_playwright()
        browser = pw.chromium.launch(
            headless=headless,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
                "--no-sandbox",
                "--disable-setuid-sandbox",
            ],
        )
        return browser

    def new_context(self, browser: Browser, domain: str) -> BrowserContext:
        """Create a browser context with saved cookies if available."""
        cookies = self.cookie_manager.get_cookies(domain)
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1366, "height": 768},
        )
        if cookies:
            try:
                context.add_cookies(cookies)
            except Exception:
                pass  # Cookies may be invalid for this domain; ignore
        return context

    def close(self) -> None:
        """Close browser and playwright."""
        if self._browser is not None:
            try:
                self._browser.close()
            except Exception:
                pass
            self._browser = None
        if self._playwright is not None:
            try:
                self._playwright.stop()
            except Exception:
                pass
            self._playwright = None


def human_delay(min_seconds: float = 1.0, max_seconds: float = 3.0) -> None:
    """Sleep for a random human-like duration."""
    time.sleep(random.uniform(min_seconds, max_seconds))


def human_type(page: Page, selector: str, text: str, min_ms: int = 50, max_ms: int = 150) -> None:
    """Type text character-by-character with random delays."""
    page.wait_for_selector(selector, timeout=10000)
    page.click(selector)
    for char in text:
        page.type(selector, char, delay=random.randint(min_ms, max_ms))
        human_delay(0.02, 0.08)


def random_mouse_move(page: Page) -> None:
    """Move mouse to a random position."""
    try:
        page.mouse.move(
            random.randint(100, 800), random.randint(100, 600)
        )
    except Exception:
        pass


def wait_for_login(
    page: Page,
    success_selector: str,
    timeout_seconds: int = 600,
    message: str | None = None,
) -> bool:
    """Wait for the user to complete manual login.

    Navigates to the login page, prints instructions, and waits until
    the success_selector appears (indicating logged in) or timeout.
    """
    if message:
        print(message)
    else:
        print(
            f"\n{'='*60}\n"
            f"PLEASE LOG IN IN THE BROWSER WINDOW\n"
            f"Complete any 2FA / captcha, then the script will detect login.\n"
            f"Waiting up to {timeout_seconds} seconds...\n"
            f"{'='*60}\n"
        )

    try:
        page.wait_for_selector(success_selector, timeout=timeout_seconds * 1000)
        print("Login detected! Saving session cookies...")
        return True
    except Exception:
        print("Login timeout - no successful login detected.")
        return False