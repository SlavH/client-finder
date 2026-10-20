"""Browser-impersonating HTTP scraper using curl_cffi with Playwright fallback.

Tries curl_cffi first (fast, lightweight). If a site blocks it (Cloudflare,
JS challenge, etc.), falls back to Playwright (full browser, handles JS and
bot detection).
"""

from __future__ import annotations

import random
import time
from typing import Any
from urllib.parse import urlparse

from curl_cffi import requests as curl_requests
from playwright.sync_api import sync_playwright

BROWSER_IMPERSONATIONS = [
    "chrome120",
    "chrome124",
    "chrome131",
    "firefox122",
    "safari17",
    "safari18",
]


class BrowserScraper:
    """HTTP client that impersonates a real browser, with Playwright fallback."""

    def __init__(
        self,
        impersonate: str = "rotate",
        rate_limit_seconds: float = 5.0,
        timeout_seconds: float = 30.0,
        max_retries: int = 3,
        respect_robots_txt: bool = True,
        playwright_headless: bool = True,
    ):
        self.impersonate = impersonate
        self.rate_limit_seconds = rate_limit_seconds
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.respect_robots_txt = respect_robots_txt
        self.playwright_headless = playwright_headless
        self._session = curl_requests.Session()
        self._session.headers.update(
            {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,"
                "image/avif,image/webp,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
                "Cache-Control": "no-cache",
            }
        )
        self._last_request_time: dict[str, float] = {}
        self._playwright = None

    # ----- curl_cffi path -----

    def _choose_impersonation(self) -> str:
        if self.impersonate == "rotate":
            return random.choice(BROWSER_IMPERSONATIONS)
        return self.impersonate

    def _domain(self, url: str) -> str:
        return urlparse(url).netloc

    def _robots_allowed(self, url: str) -> bool:
        if not self.respect_robots_txt:
            return True
        try:
            parsed = urlparse(url)
            robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
            resp = self._session.get(
                robots_url, timeout=5, impersonate="chrome120"
            )
            if resp.status_code != 200:
                return True
            if "Disallow: /" in resp.text:
                return False
        except Exception:
            pass
        return True

    def _respect_rate_limit(self, domain: str) -> None:
        now = time.time()
        last = self._last_request_time.get(domain, 0)
        elapsed = now - last
        jitter = random.uniform(0, 2.0)
        wait = max(0, self.rate_limit_seconds + jitter - elapsed)
        if wait > 0:
            time.sleep(wait)
        self._last_request_time[domain] = time.time()

    def _curl_get(self, url: str, **kwargs: Any) -> curl_requests.Response | None:
        """Fetch with curl_cffi impersonation. Returns response or None."""
        if not self._robots_allowed(url):
            return None

        domain = self._domain(url)
        self._respect_rate_limit(domain)

        headers = kwargs.pop("headers", {})
        merged_headers = dict(self._session.headers)
        merged_headers.update(headers)

        impersonate = self._choose_impersonation()

        for attempt in range(self.max_retries):
            try:
                resp = self._session.get(
                    url,
                    headers=merged_headers,
                    timeout=self.timeout_seconds,
                    impersonate=impersonate,
                    **kwargs,
                )
                if resp.status_code == 200:
                    return resp
                if resp.status_code in (403, 429, 502, 503, 504):
                    backoff = 2**attempt + random.uniform(0, 1)
                    time.sleep(min(backoff, 10))
                    impersonate = random.choice(BROWSER_IMPERSONATIONS)
                    continue
                return resp
            except Exception:
                if attempt < self.max_retries - 1:
                    time.sleep(2**attempt + random.uniform(0, 1))
                    continue
                return None
        return None

    # ----- Playwright fallback -----

    def _playwright_get(self, url: str) -> str | None:
        """Fetch with Playwright (full browser). Returns HTML text or None."""
        try:
            if self._playwright is None:
                self._playwright = sync_playwright().start()
            browser = self._playwright.chromium.launch(headless=self.playwright_headless)
            try:
                page = browser.new_page()
                page.set_extra_http_headers(
                    {
                        "Accept-Language": "en-US,en;q=0.9",
                        "Cache-Control": "no-cache",
                    }
                )
                page.goto(url, timeout=self.timeout_seconds * 1000)
                # Wait a bit for JS to render
                page.wait_for_timeout(2000)
                content = page.content()
                return content
            finally:
                browser.close()
        except Exception:
            return None

    # ----- Public API -----

    def get(self, url: str, **kwargs: Any) -> curl_requests.Response | None:
        """Fetch a URL. Tries curl_cffi first, falls back to Playwright."""
        resp = self._curl_get(url, **kwargs)
        if resp is not None and resp.status_code == 200:
            return resp
        # curl_cffi failed or non-200; try Playwright
        html = self._playwright_get(url)
        if html is not None:
            # Return a lightweight response-like object
            return _SimpleResponse(html)
        return resp  # return the curl_cffi response (may be error) or None

    def get_text(self, url: str, **kwargs: Any) -> str | None:
        """Fetch a URL and return the response text, or None on failure."""
        resp = self.get(url, **kwargs)
        if resp is None:
            return None
        if isinstance(resp, _SimpleResponse):
            return resp.text
        return resp.text

    def close(self) -> None:
        self._session.close()
        if self._playwright is not None:
            self._playwright.stop()


class _SimpleResponse:
    """Minimal response-like object for Playwright results."""

    def __init__(self, text: str):
        self.text = text
        self.status_code = 200