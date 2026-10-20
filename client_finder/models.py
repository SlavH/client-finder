"""Client finder core data models."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class Lead:
    """A potential client discovered by a source."""

    id: str
    source: str
    company: str
    name: Optional[str] = None
    role: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    website: Optional[str] = None
    url: Optional[str] = None
    contact_hint: Optional[str] = None
    fit_score: Optional[int] = None
    fit_reason: Optional[str] = None
    hook: Optional[str] = None
    pain_point: Optional[str] = None
    suggested_role: Optional[str] = None
    status: str = "new"  # new, scored, drafted, sent, replied, bounced, opted_out
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "source": self.source,
            "company": self.company,
            "name": self.name,
            "role": self.role,
            "email": self.email,
            "phone": self.phone,
            "website": self.website,
            "url": self.url,
            "contact_hint": self.contact_hint,
            "fit_score": self.fit_score,
            "fit_reason": self.fit_reason,
            "hook": self.hook,
            "pain_point": self.pain_point,
            "suggested_role": self.suggested_role,
            "status": self.status,
            "created_at": self.created_at,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Lead":
        return cls(**d)


@dataclass
class OutreachRecord:
    """A record of a message sent to a lead."""

    id: str
    lead_id: str
    channel: str  # email | linkedin | twitter | webform
    subject: Optional[str] = None
    message: Optional[str] = None
    mode: str = "email_only"  # email_only | work_first
    deliverable_path: Optional[str] = None
    sent_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    status: str = "queued"  # queued | sent | failed | bounced | replied
    response: Optional[str] = None
    dry_run: bool = True

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "lead_id": self.lead_id,
            "channel": self.channel,
            "subject": self.subject,
            "message": self.message,
            "mode": self.mode,
            "deliverable_path": self.deliverable_path,
            "sent_at": self.sent_at,
            "status": self.status,
            "response": self.response,
            "dry_run": self.dry_run,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "OutreachRecord":
        return cls(**d)


@dataclass
class ProfileContext:
    """Loaded user profile from Me/ directory."""

    resume: str = ""
    skills: dict = field(default_factory=dict)
    portfolio: dict = field(default_factory=dict)
    contact: dict = field(default_factory=dict)
    preferences: dict = field(default_factory=dict)
    tone: dict = field(default_factory=dict)

    def summary(self) -> str:
        parts = []
        if self.resume:
            parts.append(f"RESUME:\n{self.resume}")
        if self.skills:
            parts.append(f"SKILLS:\n{self.skills}")
        if self.portfolio:
            parts.append(f"PORTFOLIO:\n{self.portfolio}")
        if self.contact:
            parts.append(f"CONTACT:\n{self.contact}")
        if self.preferences:
            parts.append(f"PREFERENCES:\n{self.preferences}")
        if self.tone:
            parts.append(f"TONE:\n{self.tone}")
        return "\n\n".join(parts)