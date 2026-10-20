"""Agent orchestrator: discover → score → draft → send.

Two modes:
- email_only: draft and send cold outreach
- work_first: build a deliverable, then send it with the message
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

from client_finder.config import load_config
from client_finder.llm import LLMClient
from client_finder.models import Lead, OutreachRecord, ProfileContext
from client_finder.profile import load_profile
from client_finder.state import StateStore


def _lead_id(source: str, company: str, url: str | None) -> str:
    raw = f"{source}:{company}:{url or ''}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


class ClientFinderAgent:
    def __init__(self, me_dir: str | Path = "Me", config_path: str | Path | None = None):
        self.me_dir = Path(me_dir)
        self.config = load_config(config_path)
        self.profile = load_profile(self.me_dir)
        self.llm = LLMClient(self.config)
        self.state = StateStore(self.config.get("state", {}).get("db_path", ".client_finder_state.db"))
        self.outreach_cfg = self.config.get("outreach", {})
        self.work_cfg = self.config.get("work_first", {})
        self.sources_cfg = self.config.get("sources", {})

    # ----- public API -----

    def discover(self, sources: list[str] | None = None, limit: int = 20) -> list[dict]:
        """Run all enabled sources and return raw leads."""
        from client_finder.sources import SOURCE_REGISTRY

        if sources is None:
            sources = [k for k, v in self.sources_cfg.items() if isinstance(v, bool) and v]

        all_leads: list[dict] = []
        for source_name in sources:
            source_cls = SOURCE_REGISTRY.get(source_name)
            if source_cls is None:
                continue
            try:
                source = source_cls(config=self.sources_cfg)
                leads = source.discover(limit=limit)
                for lead in leads:
                    lead["source"] = source_name
                all_leads.extend(leads)
            except Exception as exc:  # pragma: no cover - source errors are logged
                print(f"[source:{source_name}] error: {exc}")
            finally:
                # Close scraper to release Playwright/browser resources
                try:
                    source.scraper.close()
                except Exception:
                    pass

        # Deduplicate by company+url
        seen = set()
        unique: list[dict] = []
        for lead in all_leads:
            key = f"{lead.get('company','').lower()}:{lead.get('url','')}"
            if key in seen:
                continue
            seen.add(key)
            unique.append(lead)

        # Persist new leads
        for lead in unique:
            lid = _lead_id(lead.get("source", "unknown"), lead.get("company", ""), lead.get("url"))
            lead["id"] = lid
            existing = self.state.get_lead(lid)
            if existing is None:
                lead_obj = Lead(
                    id=lid,
                    source=lead.get("source", "unknown"),
                    company=lead.get("company", ""),
                    name=lead.get("name"),
                    role=lead.get("role"),
                    email=lead.get("email"),
                    phone=lead.get("phone"),
                    website=lead.get("website"),
                    url=lead.get("url"),
                    contact_hint=lead.get("contact_hint"),
                    metadata={"raw": lead},
                )
                self.state.upsert_lead(lead_obj)

        return unique

    def score(self, limit: int = 50) -> list[dict]:
        """LLM-score new leads and return ranked results."""
        leads = self.state.list_leads(status="new", limit=limit)
        profile_summary = self.profile.summary()
        avoid = self.profile.tone.get("avoid_patterns", [])

        scored: list[dict] = []
        for lead in leads:
            lead_summary = json.dumps(
                {
                    "company": lead.company,
                    "name": lead.name,
                    "role": lead.role,
                    "website": lead.website,
                    "url": lead.url,
                    "contact_hint": lead.contact_hint,
                    "source": lead.source,
                    "metadata": lead.metadata,
                },
                indent=2,
            )
            result = self.llm.score_lead(lead_summary, profile_summary, avoid)
            if result.get("parse_error"):
                continue

            lead.fit_score = result.get("fit_score", 0)
            lead.fit_reason = result.get("fit_reason", "")
            lead.hook = result.get("hook", "")
            lead.pain_point = result.get("pain_point", "")
            lead.suggested_role = result.get("suggested_role", "")
            lead.status = "scored"
            self.state.upsert_lead(lead)

            scored.append(
                {
                    "id": lead.id,
                    "company": lead.company,
                    "fit_score": lead.fit_score,
                    "fit_reason": lead.fit_reason,
                    "hook": lead.hook,
                    "pain_point": lead.pain_point,
                    "suggested_role": lead.suggested_role,
                    "website": lead.website,
                    "url": lead.url,
                    "email": lead.email,
                    "source": lead.source,
                }
            )

        scored.sort(key=lambda x: x.get("fit_score", 0), reverse=True)
        return scored

    def draft(
        self,
        lead_id: str,
        channel: str = "email",
        mode: str | None = None,
    ) -> dict[str, Any]:
        """Draft a humanized message for a lead."""
        mode = mode or self.outreach_cfg.get("mode", "email_only")
        lead = self.state.get_lead(lead_id)
        if lead is None:
            raise ValueError(f"Lead {lead_id} not found")

        profile_summary = self.profile.summary()
        tone = self.profile.tone
        contact = self.profile.contact

        deliverable_description = None
        if mode == "work_first":
            deliv = self.llm.choose_deliverable(
                {
                    "company": lead.company,
                    "pain_point": lead.pain_point,
                    "website": lead.website,
                    "url": lead.url,
                },
                profile_summary,
                self.work_cfg.get("deliverable_types", ["mockup", "audit", "code_sample"]),
            )
            deliverable_description = deliv.get("description", "")

        draft_result = self.llm.draft_message(
            {
                "company": lead.company,
                "name": lead.name,
                "role": lead.role,
                "website": lead.website,
                "url": lead.url,
                "hook": lead.hook,
                "pain_point": lead.pain_point,
                "suggested_role": lead.suggested_role,
                "source": lead.source,
            },
            profile_summary,
            tone,
            channel,
            mode,
            deliverable_description=deliverable_description,
            contact_info=contact,
        )

        # Humanization pass
        if self.outreach_cfg.get("humanize", True):
            avoid = tone.get("avoid_patterns", [])
            body = draft_result.get("body", "")
            check = self.llm.humanize_check(body, avoid)
            if check.get("human_score", 100) < 70 and check.get("rewritten"):
                body = check["rewritten"]
                draft_result["body"] = body
                draft_result["humanized"] = True
            else:
                draft_result["humanized"] = False

        # Persist as drafted
        lead.status = "drafted"
        self.state.upsert_lead(lead)

        return {
            "lead_id": lead_id,
            "channel": channel,
            "mode": mode,
            "subject": draft_result.get("subject"),
            "body": draft_result.get("body"),
            "deliverable_description": deliverable_description,
            "humanized": draft_result.get("humanized", False),
        }

    def send(
        self,
        lead_id: str,
        channel: str,
        mode: str | None = None,
        dry_run: bool | None = None,
    ) -> dict[str, Any]:
        """Send (or dry-run) a drafted message to a lead."""
        mode = mode or self.outreach_cfg.get("mode", "email_only")
        if dry_run is None:
            dry_run = self.outreach_cfg.get("dry_run", True)

        lead = self.state.get_lead(lead_id)
        if lead is None:
            raise ValueError(f"Lead {lead_id} not found")

        # Draft if not yet drafted
        if lead.status != "drafted":
            draft = self.draft(lead_id, channel=channel, mode=mode)
        else:
            draft = {
                "lead_id": lead_id,
                "channel": channel,
                "mode": mode,
                "subject": None,
                "body": "",
                "deliverable_description": None,
            }

        # Check opt-out
        email_domain = lead.email.split("@")[-1] if lead.email else None
        if self.state.is_opted_out(lead.email, email_domain):
            lead.status = "opted_out"
            self.state.upsert_lead(lead)
            return {"status": "opted_out", "lead_id": lead_id}

        # Check daily cap
        cap = self.outreach_cfg.get("daily_caps", {}).get(channel, 999)
        today_sent = self.state.outreach_count_today(channel, dry_run=dry_run)
        if today_sent >= cap:
            return {"status": "daily_cap_reached", "channel": channel, "count": today_sent}

        # Check dedup hash
        message_body = draft.get("body", "")
        if self.state.is_sent(lead_id, channel, message_body):
            lead.status = "sent"
            self.state.upsert_lead(lead)
            return {"status": "already_sent", "lead_id": lead_id}

        # Send via channel adapter
        from client_finder.outreach import CHANNEL_REGISTRY

        channel_cls = CHANNEL_REGISTRY.get(channel)
        if channel_cls is None:
            raise ValueError(f"Unknown channel: {channel}")

        sender = channel_cls(config=self.config, dry_run=dry_run)
        result = sender.send(
            lead=lead,
            subject=draft.get("subject"),
            message=message_body,
            mode=mode,
            deliverable_description=draft.get("deliverable_description"),
        )

        # Record outreach
        record = OutreachRecord(
            id=hashlib.sha256(
                f"{lead_id}:{channel}:{datetime.utcnow().isoformat()}".encode()
            ).hexdigest()[:16],
            lead_id=lead_id,
            channel=channel,
            subject=draft.get("subject"),
            message=message_body,
            mode=mode,
            deliverable_path=result.get("deliverable_path"),
            status="sent" if not dry_run else "queued",
            dry_run=dry_run,
        )
        self.state.record_outreach(record)

        # Record dedup hash
        self.state.record_sent_hash(lead_id, channel, message_body)

        # Update lead status
        new_status = "sent" if not dry_run else "queued"
        lead.status = new_status
        self.state.upsert_lead(lead)

        return {
            "status": new_status,
            "lead_id": lead_id,
            "channel": channel,
            "dry_run": dry_run,
            "deliverable_path": result.get("deliverable_path"),
            "message": result.get("message", ""),
        }

    def run_cycle(
        self,
        sources: list[str] | None = None,
        channels: list[str] | None = None,
        mode: str | None = None,
        limit: int = 20,
        dry_run: bool | None = None,
        send: bool = False,
    ) -> dict[str, Any]:
        """Full automated cycle: discover → score → draft → send."""
        mode = mode or self.outreach_cfg.get("mode", "email_only")
        if dry_run is None:
            dry_run = not send  # if --send flag, dry_run=False

        if channels is None:
            channels = self.outreach_cfg.get("channels", ["email"])

        # 1. Discover
        discovered = self.discover(sources=sources, limit=limit)

        # 2. Score
        scored = self.score(limit=limit)

        # 3. Draft + send top leads
        results: list[dict] = []
        max_per_run = self.outreach_cfg.get("max_per_run", 20)
        for lead_info in scored[:max_per_run]:
            for channel in channels:
                # Skip channels without contact info
                if channel == "email" and not lead_info.get("email"):
                    continue
                result = self.send(
                    lead_id=lead_info["id"],
                    channel=channel,
                    mode=mode,
                    dry_run=dry_run,
                )
                results.append(result)

        return {
            "mode": mode,
            "dry_run": dry_run,
            "discovered": len(discovered),
            "scored": len(scored),
            "attempted": len(results),
            "results": results,
        }

    def list_leads(self, status: str | None = None, limit: int = 100) -> list[dict]:
        leads = self.state.list_leads(status=status, limit=limit)
        return [l.to_dict() for l in leads]

    def close(self) -> None:
        self.state.close()