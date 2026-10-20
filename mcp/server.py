"""MCP stdio server for client-finder.

Connects Claude Code, Cursor, Windsurf, and other MCP clients to the
client-finder agent. Run with:

    python mcp/server.py

Or add to Claude Code:

    claude mcp add --transport stdio client-finder -- python mcp/server.py
"""

from __future__ import annotations

import asyncio
import sys
from typing import Any

from fastmcp import FastMCP

from client_finder.agent import ClientFinderAgent

mcp = FastMCP("client-finder")

_agent: ClientFinderAgent | None = None


def _get_agent(me_dir: str = "Me") -> ClientFinderAgent:
    global _agent
    if _agent is None:
        _agent = ClientFinderAgent(me_dir=me_dir)
    return _agent


@mcp.tool()
def profile_load(me_dir: str = "Me") -> dict[str, Any]:
    """Load the user profile from the Me/ directory."""
    agent = _get_agent(me_dir)
    return {
        "resume": agent.profile.resume,
        "skills": agent.profile.skills,
        "portfolio": agent.profile.portfolio,
        "contact": agent.profile.contact,
        "preferences": agent.profile.preferences,
        "tone": agent.profile.tone,
    }


@mcp.tool()
def discover(sources: str = "github_jobs,google_maps,job_boards", limit: int = 20, me_dir: str = "Me") -> dict[str, Any]:
    """Discover client leads from configured sources."""
    agent = _get_agent(me_dir)
    source_list = [s.strip() for s in sources.split(",") if s.strip()]
    found = agent.discover(sources=source_list, limit=limit)
    return {
        "count": len(found),
        "leads": found,
    }


@mcp.tool()
def score(limit: int = 50, me_dir: str = "Me") -> dict[str, Any]:
    """LLM-score new leads and return ranked results."""
    agent = _get_agent(me_dir)
    scored = agent.score(limit=limit)
    return {
        "count": len(scored),
        "leads": scored,
    }


@mcp.tool()
def draft(
    lead_id: str,
    channel: str = "email",
    mode: str = "email_only",
    me_dir: str = "Me",
) -> dict[str, Any]:
    """Draft a humanized outreach message for a lead."""
    agent = _get_agent(me_dir)
    return agent.draft(lead_id=lead_id, channel=channel, mode=mode)


@mcp.tool()
def send(
    lead_id: str,
    channel: str,
    mode: str = "email_only",
    dry_run: bool = True,
    me_dir: str = "Me",
) -> dict[str, Any]:
    """Send (or dry-run) a message to a lead via the given channel."""
    agent = _get_agent(me_dir)
    return agent.send(lead_id=lead_id, channel=channel, mode=mode, dry_run=dry_run)


@mcp.tool()
def list_leads(status: str | None = None, limit: int = 100, me_dir: str = "Me") -> dict[str, Any]:
    """List stored leads, optionally filtered by status."""
    agent = _get_agent(me_dir)
    leads = agent.list_leads(status=status, limit=limit)
    return {"count": len(leads), "leads": leads}


@mcp.tool()
def run_cycle(
    sources: str = "github_jobs,google_maps,job_boards",
    channels: str = "email",
    mode: str = "email_only",
    limit: int = 20,
    send: bool = False,
    me_dir: str = "Me",
) -> dict[str, Any]:
    """Full automated cycle: discover → score → draft → send."""
    agent = _get_agent(me_dir)
    source_list = [s.strip() for s in sources.split(",") if s.strip()]
    channel_list = [c.strip() for c in channels.split(",") if c.strip()]
    dry_run = not send
    return agent.run_cycle(
        sources=source_list,
        channels=channel_list,
        mode=mode,
        limit=limit,
        dry_run=dry_run,
        send=send,
    )


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()