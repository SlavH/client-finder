# Legal & Compliance Disclaimer

## You are responsible

This tool automates outreach. You are solely responsible for:

- Complying with each platform's Terms of Service (LinkedIn, Twitter/X, email providers, job boards)
- Respecting `robots.txt` and website terms when scraping
- Complying with CAN-SPAM Act (US), GDPR (EU), CASL (Canada), and other anti-spam laws
- Including a physical mailing address and unsubscribe mechanism in marketing emails
- Honoring opt-out requests immediately

## Built-in safeguards (not a substitute for legal review)

- `robots.txt` is checked before scraping any domain
- Rate limits and random jitter between messages
- Daily/weekly send caps per channel
- Dry-run mode enabled by default
- Opt-out list: leads who ask to stop are never contacted again
- Dedup: the same lead is never contacted twice

## Data stays local

All profile data, lead records, sent messages, and state live in a local SQLite database on your device. Nothing is uploaded to a remote server by this tool. LLM API calls send only the lead snippet and your profile text to your chosen LLM provider.

Use responsibly.