"""CLI for client-finder."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import click

from client_finder.agent import ClientFinderAgent
from client_finder.config import load_config, load_env
from client_finder.enrich import guess_emails
from client_finder.profile import load_profile
from client_finder.state import StateStore
from client_finder.work_first import DeliverableGenerator
from client_finder.llm import LLMClient


@click.group()
def main():
    """client-finder: discover clients and send personalized outreach."""
    load_env()


@main.command()
@click.option("--me-dir", default="Me", help="Profile directory path")
def init(me_dir: str):
    """Initialize the Me/ profile directory from templates."""
    me_path = Path(me_dir)
    if me_path.exists():
        click.echo(f"{me_dir}/ already exists. Skipping.")
        return
    me_path.mkdir(parents=True, exist_ok=True)
    # Copy templates from package data? For now, just create empty files.
    templates = {
        "resume.md": "# Your Resume / Bio\n\nWrite your bio here.\n",
        "skills.yaml": "services: []\nrates:\n  hourly: 100\n  project_min: 2000\n  currency: USD\navailability: \"Open for new projects\"\ntarget:\n  industries: []\n  company_size: \"1-50 employees\"\n  locations: []\ndo_not_contact_domains: []\ndo_not_contact_keywords: []\n",
        "portfolio.yaml": "projects: []\ntestimonials: []\n",
        "contact.yaml": "name: \"Your Name\"\nemail: \"you@example.com\"\nphone: \"+1-555-000-0000\"\nwebsite: \"https://yourportfolio.com\"\naddress: \"123 Main Street, Anytown, USA\"\n",
        "preferences.yaml": "target:\n  industries: []\n  company_size: \"1-50 employees\"\n  locations: []\ndo_not_contact_domains: []\ndo_not_contact_keywords: []\n",
        "tone.yaml": 'style: "friendly, direct, no fluff"\nformality: "casual"\nlength: "short"\nhumor: 1\nopening_style: "observation"\nuse_contractions: true\navoid_patterns:\n  - "I hope this email finds you well"\nmax_paragraph_sentences: 3\nsignature: "Your Name • you@example.com • https://yourportfolio.com"\n',
    }
    for filename, content in templates.items():
        (me_path / filename).write_text(content, encoding="utf-8")
    click.echo(f"Initialized {me_dir}/ with profile templates. Edit them before running.")


@main.command()
@click.option("--config", default="config.yaml", help="Config file path")
@click.option("--me-dir", default="Me", help="Profile directory path")
def config_cmd(config: str, me_dir: str):
    """Show current configuration."""
    cfg = load_config(config)
    click.echo(json.dumps(cfg, indent=2))


@main.command()
@click.option("--sources", default="github_jobs,google_maps,job_boards", help="Comma-separated source names")
@click.option("--limit", default=20, help="Max leads per source")
@click.option("--me-dir", default="Me", help="Profile directory path")
@click.option("--config", default="config.yaml", help="Config file path")
def discover(sources: str, limit: int, me_dir: str, config: str):
    """Discover client leads from sources."""
    cfg = load_config(config)
    agent = ClientFinderAgent(me_dir=me_dir, config_path=config)
    source_list = [s.strip() for s in sources.split(",") if s.strip()]
    found = agent.discover(sources=source_list, limit=limit)
    click.echo(f"Discovered {len(found)} leads:")
    for lead in found:
        click.echo(f"  - {lead.get('company')} ({lead.get('source')}) - {lead.get('url') or 'no url'}")
    agent.close()


@main.command()
@click.option("--limit", default=50, help="Max leads to score")
@click.option("--me-dir", default="Me", help="Profile directory path")
@click.option("--config", default="config.yaml", help="Config file path")
def score(limit: int, me_dir: str, config: str):
    """LLM-score new leads."""
    agent = ClientFinderAgent(me_dir=me_dir, config_path=config)
    scored = agent.score(limit=limit)
    click.echo(f"Scored {len(scored)} leads:")
    for lead in scored:
        click.echo(
            f"  [{lead.get('fit_score', 0):3d}] {lead.get('company')} - "
            f"{lead.get('fit_reason', '')[:80]}"
        )
    agent.close()


@main.command()
@click.option("--lead-id", required=True, help="Lead ID to draft for")
@click.option("--channel", default="email", help="Outreach channel")
@click.option("--mode", default=None, help="email_only or work_first")
@click.option("--me-dir", default="Me", help="Profile directory path")
@click.option("--config", default="config.yaml", help="Config file path")
def draft(lead_id: str, channel: str, mode: str | None, me_dir: str, config: str):
    """Draft a humanized outreach message for a lead."""
    agent = ClientFinderAgent(me_dir=me_dir, config_path=config)
    result = agent.draft(lead_id=lead_id, channel=channel, mode=mode)
    click.echo(f"Channel: {result['channel']} | Mode: {result['mode']}")
    click.echo(f"Humanized: {result.get('humanized', False)}")
    if result.get("subject"):
        click.echo(f"Subject: {result['subject']}")
    click.echo(f"\n{result['body']}")
    if result.get("deliverable_description"):
        click.echo(f"\nDeliverable: {result['deliverable_description']}")
    agent.close()


@main.command()
@click.option("--lead-id", required=True, help="Lead ID to send to")
@click.option("--channel", required=True, help="Outreach channel")
@click.option("--mode", default=None, help="email_only or work_first")
@click.option("--dry-run", is_flag=True, default=True, help="Dry-run only (default)")
@click.option("--send", is_flag=True, default=False, help="Actually send the message")
@click.option("--me-dir", default="Me", help="Profile directory path")
@click.option("--config", default="config.yaml", help="Config file path")
def send(lead_id: str, channel: str, mode: str | None, dry_run: bool, send: bool, me_dir: str, config: str):
    """Send (or dry-run) a message to a lead."""
    agent = ClientFinderAgent(me_dir=me_dir, config_path=config)
    result = agent.send(
        lead_id=lead_id,
        channel=channel,
        mode=mode,
        dry_run=not send,
    )
    click.echo(json.dumps(result, indent=2))
    agent.close()


@main.command()
@click.option("--sources", default="github_jobs,google_maps,job_boards", help="Comma-separated sources")
@click.option("--channels", default="email", help="Comma-separated channels")
@click.option("--mode", default="email_only", help="email_only or work_first")
@click.option("--limit", default=20, help="Max leads to process")
@click.option("--dry-run", is_flag=True, default=True, help="Dry-run only (default)")
@click.option("--send", is_flag=True, default=False, help="Actually send messages")
@click.option("--me-dir", default="Me", help="Profile directory path")
@click.option("--config", default="config.yaml", help="Config file path")
def run(sources: str, channels: str, mode: str, limit: int, dry_run: bool, send: bool, me_dir: str, config: str):
    """Full automated cycle: discover → score → draft → send."""
    agent = ClientFinderAgent(me_dir=me_dir, config_path=config)
    source_list = [s.strip() for s in sources.split(",") if s.strip()]
    channel_list = [c.strip() for c in channels.split(",") if c.strip()]
    result = agent.run_cycle(
        sources=source_list,
        channels=channel_list,
        mode=mode,
        limit=limit,
        dry_run=not send,
        send=send,
    )
    click.echo(json.dumps(result, indent=2))
    agent.close()


@main.command()
@click.option("--status", default=None, help="Filter by lead status")
@click.option("--limit", default=100, help="Max leads to list")
@click.option("--me-dir", default="Me", help="Profile directory path")
@click.option("--config", default="config.yaml", help="Config file path")
def list_leads(status: str | None, limit: int, me_dir: str, config: str):
    """List stored leads."""
    agent = ClientFinderAgent(me_dir=me_dir, config_path=config)
    leads = agent.list_leads(status=status, limit=limit)
    click.echo(f"{len(leads)} leads:")
    for lead in leads:
        click.echo(
            f"  {lead['id']} | {lead['status']:10s} | {lead['company']} | "
            f"score={lead.get('fit_score', 'N/A')} | {lead.get('source')}"
        )
    agent.close()


@main.command()
@click.option("--lead-id", required=True, help="Lead ID")
@click.option("--deliverable-type", default="mockup", help="mockup, audit, or code_sample")
@click.option("--me-dir", default="Me", help="Profile directory path")
@click.option("--config", default="config.yaml", help="Config file path")
def deliverable(lead_id: str, deliverable_type: str, me_dir: str, config: str):
    """Generate a work-first deliverable for a lead."""
    agent = ClientFinderAgent(me_dir=me_dir, config_path=config)
    lead = agent.state.get_lead(lead_id)
    if not lead:
        click.echo(f"Lead {lead_id} not found")
        agent.close()
        return

    profile_summary = agent.profile.summary()
    gen = DeliverableGenerator(
        config=agent.work_cfg,
        llm=agent.llm,
        output_dir=agent.work_cfg.get("output_dir", "work/"),
    )
    result = gen.generate(
        lead_id=lead_id,
        company=lead.company,
        pain_point=lead.pain_point or "",
        website=lead.website,
        url=lead.url,
        profile_summary=profile_summary,
        deliverable_type=deliverable_type,
    )
    click.echo(json.dumps(result, indent=2))
    agent.close()


if __name__ == "__main__":
    main()