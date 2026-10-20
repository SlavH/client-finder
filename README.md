# client-finder

LLM-powered automated client finder and outreach tool. Runs **locally on your device**, reads your profile from `Me/`, discovers clients across multiple sources, drafts humanized messages, and sends them via email, LinkedIn, Twitter, or web forms.

## Quick start

```bash
# 1. Install
pip install -e .

# 2. Copy config examples and fill in API keys
cp config.yaml.example config.yaml
cp .env.example .env

# 3. Edit .env with your Gmail app password and LLM API key
#    Gmail: enable 2FA, then generate an App Password at
#    https://myaccount.google.com/apppasswords
#    LLM: OpenAI API key, or use Ollama locally (no key needed)

# 4. Edit Me/* with your info (already configured for Slav Hayrapetyan)
#    Me/contact.yaml - email, phone, LinkedIn
#    Me/tone.yaml - writing voice

# 5. Run a discovery cycle (dry-run by default - no emails sent)
client-finder run --sources github_jobs,google_maps --channels email --limit 20

# 6. Send for real (requires LLM API key + SMTP credentials in .env)
client-finder run --send --limit 5
```

## Gmail SMTP Setup

1. Enable 2-Factor Authentication on your Google Account
2. Go to https://myaccount.google.com/apppasswords
3. Generate an App Password for "Mail"
4. Add it to `.env`: `SMTP_PASS=your-app-password`
5. `SMTP_USER=slavhayrapetyan10@gmail.com` (already pre-filled)

## LinkedIn Setup

For LinkedIn messaging, you need either:
- **LinkedIn Access Token** - from LinkedIn Developer Portal, or
- **LinkedIn Session Cookie** - export from your browser after logging in

Add to `.env`:
```
LINKEDIN_ACCESS_TOKEN=your-token
# or
LINKEDIN_SESSION_COOKIE=your-session-cookie
```

Your LinkedIn profile (from `Me/contact.yaml`):
https://www.linkedin.com/in/slav-hayrapetyan-b867a5243

## Project layout

```
client-finder/
├── Me/                          # <-- YOUR profile (edit these files)
├── config.yaml                  # <-- your API keys, modes, rate limits
├── .env                         # <-- your secrets (never commit)
├── client_finder/           # core library
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