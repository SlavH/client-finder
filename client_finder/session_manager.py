"""Universal session manager with cookie-based persistence.

Handles login sessions for any platform that requires authentication.
First run opens a visible browser (via noVNC in Docker) for manual login + 2FA;
subsequent runs load saved cookies and run headless.
"""

from __future__ import annotations

import json
import os
import random
import time
from pathlib import Path
from typing import Any

from playwright.sync_api import sync_playwright, Browser, BrowserContext, Page

from client_finder.novnc_launcher import NovncLauncher, check_novnc_available, is_docker


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
    """Launches Playwright browsers with session cookie support.

    When cookies don't exist (first login), uses noVNC (in Docker) or
    headed browser (on desktop) for manual login. When cookies exist,
    launches headless Chromium with cookies injected.
    """

    def __init__(
        self,
        cookie_manager: CookieManager,
        headless_after_login: bool = True,
        login_timeout_seconds: int = 600,
        session_check_timeout_seconds: int = 10,
        use_novnc: bool | None = None,
        novnc_config: dict[str, Any] | None = None,
    ):
        self.cookie_manager = cookie_manager
        self.headless_after_login = headless_after_login
        self.login_timeout_seconds = login_timeout_seconds
        self.session_check_timeout_seconds = session_check_timeout_seconds
        self._playwright = None
        self._browser: Browser | None = None
        self._novnc: NovncLauncher | None = None

        # Auto-detect: use noVNC if in Docker and noVNC is available
        if use_novnc is None:
            self.use_novnc = is_docker() and check_novnc_available()
        else:
            self.use_novnc = use_novnc

        # Store novnc config for the launcher
        self.novnc_config = novnc_config or {}

    def _get_playwright(self):
        if self._playwright is None:
            self._playwright = sync_playwright().start()
        return self._playwright

    def _launch_playwright_browser(self, headless: bool = False) -> Browser:
        """Launch a Playwright Chromium browser instance."""
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

    def launch_with_login(
        self,
        domain: str,
        login_url: str,
        success_selector: str,
        login_message: str | None = None,
    ) -> tuple[Browser, BrowserContext]:
        """Launch browser, ensure login, return (browser, context) with valid cookies.

        If cookies exist and session is valid → headless browser with cookies.
        If no cookies or session invalid → noVNC/manual login flow → save cookies → headless.
        """
        cookies = self.cookie_manager.get_cookies(domain)

        if cookies:
            # Try headless with existing cookies first
            browser = self._launch_playwright_browser(headless=self.headless_after_login)
            context = self.new_context(browser, domain)
            page = context.new_page()
            try:
                page.goto(login_url, timeout=30000)
                # Quick check: is session still valid?
                try:
                    page.wait_for_selector(success_selector, timeout=self.session_check_timeout_seconds * 1000)
                    # Session valid, return context
                    page.close()
                    return browser, context
                except Exception:
                    # Session expired, need re-login
                    page.close()
                    context.close()
                    browser.close()
            except Exception:
                page.close()
                context.close()
                browser.close()

        # Need manual login via noVNC or headed browser
        return self._manual_login_flow(domain, login_url, success_selector, login_message)

    def _manual_login_flow(
        self,
        domain: str,
        login_url: str,
        success_selector: str,
        login_message: str | None = None,
    ) -> tuple[Browser, BrowserContext]:
        """Run manual login flow: noVNC (Docker) or headed browser (desktop).

        Returns (browser, context) with valid cookies saved.
        """

        if self.use_novnc:
            # Use noVNC for Docker environment
            self._novnc = NovncLauncher(
                vnc_port=self.novnc_config.get("vnc_port", 5900),
                websockify_port=self.novnc_config.get("websockify_port", 6080),
                novnc_path=self.novnc_config.get("novnc_path", "/usr/share/novnc"),
                display=self.novnc_config.get("display", ":99"),
                login_timeout_seconds=self.login_timeout_seconds,
            )
            novnc_url = self._novnc.start(login_url=login_url)
            print(f"\n{'='*70}")
            print(f"noVNC URL: {novnc_url}")
            print(f"Open this URL in your browser to log in to {login_url}")
            print(f"Complete any 2FA / captcha, then come back here.")
            print(f"{'='*70}\n")

            ok = self._novnc.wait_for_login(message=login_message)
            if not ok:
                self._novnc.stop()
                raise RuntimeError("Login timeout or cancelled")

            # Save cookies from noVNC Chromium
            # The noVNC launcher uses system chromium, not Playwright.
            # We need to get cookies from the running Chromium via Playwright
            # connecting to the same display, or re-open with Playwright headed.
            # Simplest: launch Playwright headed (now that user is logged in)
            # and cookies should be in the user data dir.
            # Actually, let's use Playwright headed to capture cookies.
            self._novnc.stop()

        # Launch Playwright headed browser (now user should be logged in via noVNC
        # cookies, or this is a desktop environment with display)
        browser = self._launch_playwright_browser(headless=False)
        context = self.new_context(browser, domain)
        page = context.new_page()

        try:
            page.goto(login_url, timeout=30000)
            # Wait for session to be valid
            page.wait_for_selector(success_selector, timeout=self.session_check_timeout_seconds * 1000)
            # Save cookies
            cookies = context.cookies()
            self.cookie_manager.save_cookies(domain, cookies)
            print(f"Session cookies saved for {domain}")
            return browser, context
        except Exception as exc:
            page.close()
            context.close()
            browser.close()
            raise RuntimeError(f"Login verification failed: {exc}")

    def launch_headless(self, domain: str) -> tuple[Browser, BrowserContext]:
        """Launch headless browser with saved cookies (no login needed)."""
        browser = self._launch_playwright_browser(headless=self.headless_after_login)
        context = self.new_context(browser, domain)
        return browser, context

    def close(self) -> None:
        """Close browser, playwright, and noVNC."""
        if self._novnc is not None:
            try:
                self._novnc.stop()
            except Exception:
                pass
            self._novnc = None
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