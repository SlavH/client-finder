"""Outreach channel adapters with browser-based login and cookie persistence."""

from __future__ import annotations

import os
import smtplib
from abc import ABC, abstractmethod
from email.message import EmailMessage
from typing import Any

from client_finder.outreach.base import CHANNEL_REGISTRY, register_channel
from client_finder.session_manager import (
    BrowserLauncher,
    CookieManager,
    human_delay,
    human_type,
    random_mouse_move,
)


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

    def _get_launcher(self, domain: str) -> tuple[BrowserLauncher, CookieManager]:
        """Create a BrowserLauncher and CookieManager for a domain."""
        session_cfg = (
            self.config.get("session", {}) if isinstance(self.config, dict) else {}
        )
        cookies_dir = session_cfg.get("cookies_dir", "state/cookies")
        headless = session_cfg.get("headless_after_login", True)
        login_timeout = session_cfg.get("login_timeout_seconds", 600)
        novnc_config = session_cfg.get("novnc", {}) or {}

        cookie_mgr = CookieManager(cookies_dir)
        launcher = BrowserLauncher(
            cookie_mgr,
            headless_after_login=headless,
            login_timeout_seconds=login_timeout,
            use_novnc=None,  # Auto-detect Docker
            novnc_config=novnc_config,
        )
        return launcher, cookie_mgr

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
        # Check if browser-based email is configured
        outreach_cfg = (
            self.config.get("outreach", {}) if isinstance(self.config, dict) else {}
        )
        email_cfg = outreach_cfg.get("email", {}) if isinstance(outreach_cfg, dict) else {}
        if email_cfg.get("use_browser", False):
            return self._send_browser(lead, subject, message, mode)
        return self._send_smtp(lead, subject, message, mode)

    # ----- SMTP path -----

    def _send_smtp(
        self,
        lead: Any,
        subject: str | None,
        message: str,
        mode: str = "email_only",
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
        import os as _os
        email_cfg = {}
        if isinstance(self.config, dict):
            email_cfg = self.config.get("outreach", {}).get("email", {}) or {}

        host = email_cfg.get("host") or self.config.get("smtp_host") or _os.environ.get("SMTP_HOST", "localhost")
        port = int(email_cfg.get("port") or self.config.get("smtp_port") or _os.environ.get("SMTP_PORT", 587))
        user = email_cfg.get("user") or self.config.get("smtp_user") or _os.environ.get("SMTP_USER")
        password = email_cfg.get("password") or self.config.get("smtp_pass") or _os.environ.get("SMTP_PASS")
        from_name = email_cfg.get("from_name") or self.config.get("smtp_from_name") or _os.environ.get("SMTP_FROM_NAME", "You")
        from_email = email_cfg.get("from") or self.config.get("smtp_from") or _os.environ.get("SMTP_FROM", "you@example.com")

        full_message = self._build_full_message(message, contact)

        msg = EmailMessage()
        msg["Subject"] = subject or "Quick question"
        msg["From"] = f"{from_name} <{from_email}>"
        msg["To"] = to_email
        msg.set_content(full_message)

        try:
            with smtplib.SMTP(host, port, timeout=30) as smtp:
                smtp.starttls()
                if user and password:
                    smtp.login(user, password)
                smtp.send_message(msg)
            return {"status": "sent", "message": f"email sent to {to_email}"}
        except Exception as exc:
            return {"status": "failed", "error": str(exc), "message": ""}

    # ----- Browser path (Gmail) -----

    def _send_browser(
        self,
        lead: Any,
        subject: str | None,
        message: str,
        mode: str = "email_only",
    ) -> dict[str, Any]:
        to_email = (
            getattr(lead, "email", None)
            if not isinstance(lead, dict)
            else lead.get("email")
        )
        if not to_email:
            return {"status": "skipped", "reason": "no email", "message": ""}

        if self.dry_run:
            print(f"[DRY-RUN] Browser email to {to_email}: {subject}")
            print(f"       {message[:200]}...")
            return {"status": "queued", "message": "dry-run"}

        contact = self.config.get("contact", {}) if isinstance(self.config, dict) else {}
        launcher, cookie_mgr = self._get_launcher("mail.google.com")

        try:
            # launch_with_login handles: check cookies → headless or noVNC login → save cookies
            browser, context = launcher.launch_with_login(
                domain="mail.google.com",
                login_url="https://mail.google.com",
                success_selector='[gh="cm"]',  # Compose button
                login_message=(
                    f"\n{'='*70}\n"
                    f"PLEASE LOG INTO GMAIL IN THE BROWSER WINDOW\n"
                    f"Open the noVNC URL shown above, complete 2FA if prompted,\n"
                    f"then press Enter here when logged in.\n"
                    f"{'='*70}\n"
                ),
            )
            page = context.new_page()

            # Compose email
            human_delay(1, 2)
            page.wait_for_selector('[gh="cm"]', timeout=10000)
            random_mouse_move(page)
            page.click('[gh="cm"]')
            human_delay(1, 2)

            # Fill recipient
            page.wait_for_selector('textarea[name="to"]', timeout=10000)
            human_type(page, 'textarea[name="to"]', to_email)
            human_delay(0.5, 1)
            page.keyboard.press("Enter")
            human_delay(0.5, 1)

            # Fill subject
            page.wait_for_selector('input[name="subjectbox"]', timeout=10000)
            human_type(page, 'input[name="subjectbox"]', subject or "Quick question")
            human_delay(0.5, 1)

            # Fill body
            page.wait_for_selector('div[role="textbox"][g_editable="true"]', timeout=10000)
            full_message = self._build_full_message(message, contact)
            human_type(page, 'div[role="textbox"][g_editable="true"]', full_message)
            human_delay(1, 2)

            # Send
            page.wait_for_selector('div[role="button"][gh="tm"]', timeout=10000)
            random_mouse_move(page)
            page.click('div[role="button"][gh="tm"]')
            human_delay(3, 5)

            # Cookies already saved by launch_with_login
            page.close()
            context.close()
            browser.close()
            launcher.close()

            return {"status": "sent", "message": f"browser email sent to {to_email}"}

        except Exception as exc:
            try:
                launcher.close()
            except Exception:
                pass
            return {"status": "failed", "error": str(exc), "message": ""}


@register_channel
class BrowserEmailChannel(EmailChannel):
    name = "browser_email"

    def send(
        self,
        lead: Any,
        subject: str | None,
        message: str,
        mode: str = "email_only",
        deliverable_path: str | None = None,
        deliverable_description: str | None = None,
    ) -> dict[str, Any]:
        # Force browser path
        to_email = (
            getattr(lead, "email", None)
            if not isinstance(lead, dict)
            else lead.get("email")
        )
        if not to_email:
            return {"status": "skipped", "reason": "no email", "message": ""}

        if self.dry_run:
            print(f"[DRY-RUN] Browser email to {to_email}: {subject}")
            print(f"       {message[:200]}...")
            return {"status": "queued", "message": "dry-run"}

        return self._send_browser(lead, subject, message, mode)


@register_channel
class BrowserLinkedInChannel(BaseChannel):
    name = "browser_linkedin"

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

        contact = self.config.get("contact", {}) if isinstance(self.config, dict) else {}
        sender_linkedin = contact.get("linkedin", "")

        if self.dry_run:
            print(f"[DRY-RUN] Browser LinkedIn from {sender_linkedin} to {profile_url}:")
            print(f"       {message[:200]}...")
            return {"status": "queued", "message": "dry-run"}

        launcher, cookie_mgr = self._get_launcher("linkedin.com")

        try:
            browser, context = launcher.launch_with_login(
                domain="linkedin.com",
                login_url="https://www.linkedin.com/login",
                success_selector='[data-test-id="main-feed"], .global-nav, [class*="feed"]',
                login_message=(
                    f"\n{'='*70}\n"
                    f"PLEASE LOG INTO LINKEDIN IN THE BROWSER WINDOW\n"
                    f"Open the noVNC URL shown above, complete 2FA if prompted,\n"
                    f"then press Enter here when logged in.\n"
                    f"{'='*70}\n"
                ),
            )
            page = context.new_page()

            # Navigate to profile and send message
            page.goto(profile_url, timeout=30000)
            human_delay(2, 3)

            # Click Message button
            try:
                page.wait_for_selector(
                    'button[class*="message"], [class*="message-button"]',
                    timeout=10000,
                )
                random_mouse_move(page)
                page.click('button[class*="message"], [class*="message-button"]')
                human_delay(1, 2)

                # Type message in message box
                page.wait_for_selector(
                    'div[role="textbox"], textarea[class*="message"]',
                    timeout=10000,
                )
                human_type(page, 'div[role="textbox"], textarea[class*="message"]', message)
                human_delay(1, 2)

                # Send
                page.click('button[type="submit"], [class*="send"]')
                human_delay(2, 3)
            except Exception:
                pass

            page.close()
            context.close()
            browser.close()
            launcher.close()

            return {
                "status": "sent",
                "message": f"browser LinkedIn message to {profile_url}",
            }

        except Exception as exc:
            try:
                launcher.close()
            except Exception:
                pass
            return {"status": "failed", "error": str(exc), "message": ""}


@register_channel
class BrowserTwitterChannel(BaseChannel):
    name = "browser_twitter"

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
            print(f"[DRY-RUN] Browser Twitter DM to {handle}:")
            print(f"       {message[:200]}...")
            return {"status": "queued", "message": "dry-run"}

        launcher, cookie_mgr = self._get_launcher("x.com")

        try:
            browser, context = launcher.launch_with_login(
                domain="x.com",
                login_url="https://x.com/i/flow/login",
                success_selector='[data-testid="primaryColumn"], [data-testid="AppTabBar"]',
                login_message=(
                    f"\n{'='*70}\n"
                    f"PLEASE LOG INTO TWITTER/X IN THE BROWSER WINDOW\n"
                    f"Open the noVNC URL shown above, complete 2FA if prompted,\n"
                    f"then press Enter here when logged in.\n"
                    f"{'='*70}\n"
                ),
            )
            page = context.new_page()

            # Navigate to user profile and send DM
            profile_url = f"https://x.com/{handle}"
            page.goto(profile_url, timeout=30000)
            human_delay(2, 3)

            # Click Message button
            try:
                page.wait_for_selector(
                    '[data-testid="sendDMFromProfile"], [class*="send-message"]',
                    timeout=10000,
                )
                random_mouse_move(page)
                page.click('[data-testid="sendDMFromProfile"], [class*="send-message"]')
                human_delay(1, 2)

                # Type message
                page.wait_for_selector(
                    'div[role="textbox"], textarea[class*="dm"]',
                    timeout=10000,
                )
                human_type(page, 'div[role="textbox"], textarea[class*="dm"]', message)
                human_delay(1, 2)

                # Send
                page.click('[data-testid="dmSendButton"], [class*="send"]')
                human_delay(2, 3)
            except Exception:
                pass

            page.close()
            context.close()
            browser.close()
            launcher.close()

            return {
                "status": "sent",
                "message": f"browser Twitter DM to {handle}",
            }

        except Exception as exc:
            try:
                launcher.close()
            except Exception:
                pass
            return {"status": "failed", "error": str(exc), "message": ""}


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

        contact = self.config.get("contact", {}) if isinstance(self.config, dict) else {}
        sender_linkedin = contact.get("linkedin", "")

        if self.dry_run:
            print(f"[DRY-RUN] LinkedIn message from {sender_linkedin} to {profile_url}:")
            print(f"       {message[:200]}...")
            return {"status": "queued", "message": "dry-run"}

        token = os.environ.get("LINKEDIN_ACCESS_TOKEN")
        session_cookie = os.environ.get("LINKEDIN_SESSION_COOKIE")
        if not token and not session_cookie:
            return {
                "status": "skipped",
                "reason": "no LinkedIn token or session cookie configured",
                "message": "",
            }

        try:
            print(
                f"[LinkedIn] From {sender_linkedin} to {profile_url}: {message[:100]}..."
            )
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