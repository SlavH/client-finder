---
name: client-finder
description: Discover clients and send personalized outreach via email, LinkedIn, Twitter, or web forms
metadata:
  opencode/autoinvoke: "false"
---

# client-finder Skill

This skill helps you discover potential clients and send personalized outreach messages.

## When to use

Use this skill when you want to:
- Find new client leads from job boards, Google Maps, GitHub Jobs, LinkedIn
- Score leads by fit using an LLM
- Draft humanized, personalized outreach emails/messages
- Send outreach via email, LinkedIn, Twitter, or web contact forms
- Run work-first campaigns (build a mockup/audit/code sample, then send)

## Profile

Before using, fill out the `Me/` directory in this project:
- `Me/resume.md` - your bio and experience
- `Me/skills.yaml` - your services, rates, target industries
- `Me/contact.yaml` - your email, phone, website, address
- `Me/preferences.yaml` - target industries, do-not-contact rules
- `Me/tone.yaml` - your writing voice and phrases to avoid

## Configuration

Copy `config.yaml.example` to `config.yaml` and `.env.example` to `.env`,
then fill in your LLM API key and SMTP credentials.

## Workflow

1. `client-finder discover` - find leads from sources
2. `client-finder score` - LLM scores and ranks leads
3. `client-finder draft --lead-id <id> --channel email` - draft a message
4. `client-finder send --lead-id <id> --channel email` - send (dry-run by default)
5. `client-finder run --send` - full automated cycle (discover → score → draft → send)

## Modes

- `email_only` (default): draft and send cold outreach asking for a meeting
- `work_first`: build a deliverable (mockup, audit, code sample), then send it

## Safety

- Dry-run is enabled by default. Use `--send` to actually send messages.
- Rate limits, robots.txt respect, opt-out tracking, and daily caps are enforced.
- You are responsible for complying with platform ToS and anti-spam laws.

## Available commands

Run these from the project root:

```
client-finder init --me-dir ./Me
client-finder discover --sources github_jobs,google_maps --limit 20
client-finder score --limit 50
client-finder draft --lead-id <id> --channel email --mode email_only
client-finder send --lead-id <id> --channel email --dry-run
client-finder run --sources github_jobs,google_maps --channels email --limit 20 --send
client-finder list-leads --status new
```

## MCP

This project also includes an MCP stdio server at `mcp/server.py` for use
with Claude Code, Cursor, Windsurf, and other MCP-compatible clients.