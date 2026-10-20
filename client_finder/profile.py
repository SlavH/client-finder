"""Profile loading from Me/ directory."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from client_finder.models import ProfileContext


def load_profile(me_dir: str | Path) -> ProfileContext:
    """Load all profile files from the Me/ directory."""
    me_dir = Path(me_dir)
    ctx = ProfileContext()

    resume_path = me_dir / "resume.md"
    if resume_path.exists():
        ctx.resume = resume_path.read_text(encoding="utf-8").strip()

    skills_path = me_dir / "skills.yaml"
    if skills_path.exists():
        ctx.skills = _load_yaml(skills_path)

    portfolio_path = me_dir / "portfolio.yaml"
    if portfolio_path.exists():
        ctx.portfolio = _load_yaml(portfolio_path)

    contact_path = me_dir / "contact.yaml"
    if contact_path.exists():
        ctx.contact = _load_yaml(contact_path)

    preferences_path = me_dir / "preferences.yaml"
    if preferences_path.exists():
        ctx.preferences = _load_yaml(preferences_path)

    tone_path = me_dir / "tone.yaml"
    if tone_path.exists():
        ctx.tone = _load_yaml(tone_path)

    return ctx


def _load_yaml(path: Path) -> dict[str, Any]:
    try:
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}