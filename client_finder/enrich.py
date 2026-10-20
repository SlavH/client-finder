"""Email/phone enrichment utilities."""

from __future__ import annotations

from typing import Any

EMAIL_PATTERNS = [
    "{first}@{domain}",
    "{first}.{last}@{domain}",
    "{first}{last}@{domain}",
    "{first}_{last}@{domain}",
    "{last}@{domain}",
    "{first}@{domain}",
]


def guess_emails(name: str | None, domain: str | None) -> list[str]:
    """Guess likely email addresses for a person at a domain."""
    if not name or not domain:
        return []
    parts = name.lower().split()
    first = parts[0] if parts else ""
    last = parts[-1] if len(parts) > 1 else ""
    emails: set[str] = set()
    for pattern in EMAIL_PATTERNS:
        email = pattern.format(first=first, last=last, domain=domain)
        emails.add(email)
    return sorted(emails)


def extract_domain(url_or_email: str | None) -> str | None:
    if not url_or_email:
        return None
    if "@" in url_or_email:
        return url_or_email.split("@")[-1].strip()
    if url_or_email.startswith("http"):
        from urllib.parse import urlparse
        return urlparse(url_or_email).netloc
    return url_or_email.strip()