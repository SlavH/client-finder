# client-finder

LLM-powered automated client finder and outreach tool. Runs **locally on your device**, reads your profile from `Me/`, discovers clients across multiple sources, drafts humanized messages, and sends them via email, LinkedIn, Twitter, or web forms.

## Quick start

```bash
# 1. Install
pip install -e .

# 2. Initialize your profile folder
client-finder init --me-dir ./Me

# 3. Edit Me/* with your info (resume.md, skills.yaml, contact.yaml, preferences.yaml, tone.yaml)

# 4. Copy config examples and fill in API keys
cp config.yaml.example config.yaml
cp .env.example .env

# 5. Run a discovery cycle (dry-run by default - no emails sent)
client-finder run --sources github_jobs,google_maps,job_boards --channels email --limit 20

# 6. Send for real
client-finder run --send --limit 5
```

## Project layout

```
client-finder/
├── Me/                          # <-- YOUR profile (edit these files)
├── config.yaml                  # <-- your API keys, modes, rate limits
├── .env                         # <-- your secrets (never commit)
├── src/client_finder/           # core library
├── mcp/server.py                # stdio MCP server for Claude Code / Cursor
├── opencode/.opencode/skills/client-finder/  # Opencode skill
├── claude/.mcp.json.example     # Claude Code config
└── LEGAL.md                     # ToS/GDPR/CAN-SPAM disclaimers
```

## Modes

- `email_only` — draft and send cold outreach asking for a meeting
- `work_first` — build a deliverable (mockup, audit, code sample), then send it with the message

## Plugin support

- **Claude Code / Cursor / Windsurf**: add the stdio MCP server via `.mcp.json`
- **Opencode**: load the `.opencode/skills/client-finder/` skill

## Safety

Dry-run is enabled by default. Rate limits, robots.txt respect, opt-out tracking, and daily send caps are enforced. You are responsible for complying with platform ToS and anti-spam laws.