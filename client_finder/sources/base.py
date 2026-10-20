"""Pluggable lead discovery sources - base class and registry."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from bs4 import BeautifulSoup

from client_finder.scraper import BrowserScraper

SOURCE_REGISTRY: dict[str, type["BaseSource"]] = {}


def register_source(cls: type["BaseSource"]) -> type["BaseSource"]:
    SOURCE_REGISTRY[cls.name] = cls
    return cls


class BaseSource(ABC):
    name: str = "base"

    def __init__(self, config: dict[str, Any] | None = None):
        self.config = config or {}
        scraping_cfg = self.config.get("scraping", {})
        self.scraper = BrowserScraper(
            impersonate=scraping_cfg.get("impersonate", "rotate"),
            rate_limit_seconds=scraping_cfg.get("rate_limit_seconds", 5.0),
            timeout_seconds=scraping_cfg.get("timeout_seconds", 30.0),
            max_retries=scraping_cfg.get("max_retries", 3),
            respect_robots_txt=scraping_cfg.get("respect_robots_txt", True),
        )

    def _fetch(self, url: str) -> str | None:
        """Fetch a URL with browser impersonation. Returns HTML text or None."""
        return self.scraper.get_text(url)

    def _parse(self, html: str) -> BeautifulSoup:
        return BeautifulSoup(html, "html.parser")

    @abstractmethod
    def discover(self, limit: int = 20) -> list[dict[str, Any]]:
        ...


@register_source
class GitHubJobsSource(BaseSource):
    name = "github_jobs"

    def discover(self, limit: int = 20) -> list[dict[str, Any]]:
        leads: list[dict[str, Any]] = []
        search_urls = ["https://remoteok.com/remote-dev-jobs"]
        for url in search_urls:
            html = self._fetch(url)
            if not html:
                continue
            soup = self._parse(html)
            for row in soup.select("tr.job")[:limit]:
                company_el = row.select_one("td.company h3")
                title_el = row.select_one("td.position h2")
                link_el = row.select_one("td.position a")
                if not company_el or not title_el:
                    continue
                company = company_el.get_text(strip=True)
                title = title_el.get_text(strip=True)
                link = link_el.get("href") if link_el else None
                if link and link.startswith("/"):
                    link = "https://remoteok.com" + link
                leads.append(
                    {
                        "company": company,
                        "role": title,
                        "url": link,
                        "contact_hint": None,
                        "metadata": {"type": "job_posting"},
                    }
                )
                if len(leads) >= limit:
                    break
        return leads


@register_source
class GoogleMapsSource(BaseSource):
    name = "google_maps"

    def discover(self, limit: int = 20) -> list[dict[str, Any]]:
        leads: list[dict[str, Any]] = []
        queries = [
            "web developer near me",
            "small business website designer",
            "local business website redesign",
        ]
        for query in queries:
            url = f"https://www.google.com/maps/search/{query.replace(' ', '+')}"
            html = self._fetch(url)
            if not html:
                continue
            soup = self._parse(html)
            for card in soup.select("div.Nv2PK")[:limit]:
                name_el = card.select_one("div.qBF1Pd")
                if not name_el:
                    continue
                company = name_el.get_text(strip=True)
                link_el = card.select_one("a")
                url = link_el.get("href") if link_el else None
                leads.append(
                    {
                        "company": company,
                        "role": "Business Owner",
                        "website": url,
                        "url": url,
                        "contact_hint": None,
                        "metadata": {"type": "local_business", "query": query},
                    }
                )
                if len(leads) >= limit:
                    break
        return leads


@register_source
class JobBoardsSource(BaseSource):
    name = "job_boards"

    def discover(self, limit: int = 20) -> list[dict[str, Any]]:
        leads: list[dict[str, Any]] = []
        url = "https://wellfound.com/role/full-stack-developer"
        html = self._fetch(url)
        if html:
            soup = self._parse(html)
            for card in soup.select("div.job")[:limit]:
                title_el = card.select_one("h3")
                company_el = card.select_one("h4")
                link_el = card.select_one("a")
                if not title_el or not company_el:
                    continue
                company = company_el.get_text(strip=True)
                title = title_el.get_text(strip=True)
                link = link_el.get("href") if link_el else None
                if link and link.startswith("/"):
                    link = "https://wellfound.com" + link
                leads.append(
                    {
                        "company": company,
                        "role": title,
                        "url": link,
                        "contact_hint": None,
                        "metadata": {"type": "job_posting"},
                    }
                )
        return leads


@register_source
class LinkedInSource(BaseSource):
    name = "linkedin"

    def discover(self, limit: int = 20) -> list[dict[str, Any]]:
        # LinkedIn heavily blocks scraping; placeholder for authenticated sessions/API
        # curl_cffi impersonation helps but LinkedIn typically requires auth.
        return []