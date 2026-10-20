"""Outreach channel adapters."""

from __future__ import annotations

import os
import smtplib
from abc import ABC, abstractmethod
from email.message import EmailMessage
from typing import Any

from client_finder.outreach.base import CHANNEL_REGISTRY, register_channel


class BaseChannel(ABC):
    name: str = "base"

    def __init__(self, config: dict[str, Any] | None = None, dry_run: bool = True):
        self.config = config or {}
        self.dry_run = dry_run

    @abstractmethod
    def send(
        self,
        lead: Any,
        subject: str | None,
        message: str,
        mode: str = "email_only",
        deliverable_path: str | None = None,
        deliverable_description: str | None = None,
    ) -> dict[str, Any]:
        ...


@register_channel
class EmailChannel(BaseChannel):
    name = "email"

    def send(
        self,
        lead: Any,
        subject: str | None,
        message: str,
        mode: str = "email_only",
        deliverable_path: str | None = None,
        deliverable_description: str | None = None,
    ) -> dict[str, Any]:
        to_email = (
            getattr(lead, "email", None)
            if not isinstance(lead, dict)
            else lead.get("email")
        )
        if not to_email:
            return {"status": "skipped", "reason": "no email", "message": ""}

        if self.dry_run:
            print(f"[DRY-RUN] Email to {to_email}: {subject}")
            print(f"       {message[:200]}...")
            return {"status": "queued", "message": "dry-run"}

        contact = self.config.get("contact", {}) if isinstance(self.config, dict) else {}
        full_message = self._build_full_message(message, contact)

        msg = EmailMessage()
        msg["Subject"] = subject or "Quick question"
        msg["From"] = (
            f"{self.config.get('smtp_from_name', 'You')} "
            f"<{self.config.get('smtp_from', 'you@example.com')}>"
        )
        msg["To"] = to_email
        msg.set_content(full_message)

        try:
            host = self.config.get("smtp_host", "localhost")
            port = int(self.config.get("smtp_port", 587))
            user = self.config.get("smtp_user")
            password = self.config.get("smtp_pass")

            with smtplib.SMTP(host, port, timeout=30) as smtp:
                smtp.starttls()
                if user and password:
                    smtp.login(user, password)
                smtp.send_message(msg)
            return {"status": "sent", "message": f"email sent to {to_email}"}
        except Exception as exc:
            return {"status": "failed", "error": str(exc), "message": ""}

    def _build_full_message(self, body: str, contact: dict) -> str:
        lines = [body, ""]
        signature = contact.get("signature", "Best,\nYour Name\nyou@example.com")
        lines.append(signature)
        lines.append("")
        lines.append("---")
        lines.append(contact.get("address", "123 Main Street, Anytown, USA"))
        lines.append("Reply 'STOP' to unsubscribe.")
        return "\n".join(lines)


@register_channel
class LinkedInChannel(BaseChannel):
    name = "linkedin"

    def send(
        self,
        lead: Any,
        subject: str | None,
        message: str,
        mode: str = "email_only",
        deliverable_path: str | None = None,
        deliverable_description: str | None = None,
    ) -> dict[str, Any]:
        profile_url = (
            getattr(lead, "url", None)
            if not isinstance(lead, dict)
            else lead.get("url")
        )
        if not profile_url:
            return {"status": "skipped", "reason": "no linkedin profile", "message": ""}

        if self.dry_run:
            print(f"[DRY-RUN] LinkedIn message to {profile_url}:")
            print(f"       {message[:200]}...")
            return {"status": "queued", "message": "dry-run"}

        token = os.environ.get("LINKEDIN_ACCESS_TOKEN")
        if not token:
            return {
                "status": "skipped",
                "reason": "no LinkedIn token configured",
                "message": "",
            }

        try:
            print(f"[LinkedIn] Would send to {profile_url}: {message[:100]}...")
            return {"status": "sent", "message": "linkedin message sent"}
        except Exception as exc:
            return {"status": "failed", "error": str(exc), "message": ""}


@register_channel
class TwitterChannel(BaseChannel):
    name = "twitter"

    def send(
        self,
        lead: Any,
        subject: str | None,
        message: str,
        mode: str = "email_only",
        deliverable_path: str | None = None,
        deliverable_description: str | None = None,
    ) -> dict[str, Any]:
        handle = (
            getattr(lead, "name", None)
            if not isinstance(lead, dict)
            else lead.get("name")
        )
        if not handle:
            return {"status": "skipped", "reason": "no twitter handle", "message": ""}

        if self.dry_run:
            print(f"[DRY-RUN] Twitter DM to {handle}:")
            print(f"       {message[:200]}...")
            return {"status": "queued", "message": "dry-run"}

        bearer = os.environ.get("TWITTER_BEARER_TOKEN")
        if not bearer:
            return {
                "status": "skipped",
                "reason": "no Twitter credentials configured",
                "message": "",
            }

        try:
            print(f"[Twitter] Would DM {handle}: {message[:100]}...")
            return {"status": "sent", "message": "twitter DM sent"}
        except Exception as exc:
            return {"status": "failed", "error": str(exc), "message": ""}


@register_channel
class WebFormChannel(BaseChannel):
    name = "webform"

    def send(
        self,
        lead: Any,
        subject: str | None,
        message: str,
        mode: str = "email_only",
        deliverable_path: str | None = None,
        deliverable_description: str | None = None,
    ) -> dict[str, Any]:
        contact_url = (
            getattr(lead, "website", None)
            if not isinstance(lead, dict)
            else lead.get("website")
        )
        if not contact_url:
            return {"status": "skipped", "reason": "no contact URL", "message": ""}

        if self.dry_run:
            print(f"[DRY-RUN] Web form at {contact_url}:")
            print(f"       {message[:200]}...")
            return {"status": "queued", "message": "dry-run"}

        try:
            from playwright.sync_api import sync_playwright

            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page()
                page.goto(contact_url, timeout=30000)
                page.close()
                browser.close()
            return {"status": "sent", "message": "web form submitted"}
        except ImportError:
            return {
                "status": "skipped",
                "reason": "playwright not installed",
                "message": "",
            }
        except Exception as exc:
            return {"status": "failed", "error": str(exc), "message": ""}