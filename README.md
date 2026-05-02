# Zeplin Lead System

Lead intelligence panel for Zeplin Media. It scrapes local businesses from Google Maps, audits their digital presence, matches Zeplin services, generates sales notes, and publishes a static dashboard.

## Setup

```bash
python3 -m venv venv
venv/bin/pip install -r requirements.txt
cp .env.example .env
venv/bin/playwright install chromium
```

Add `GROQ_API_KEY` to `.env` for AI report generation.

## Common Commands

Normalize existing leads and rebuild the dashboard:

```bash
venv/bin/python scripts/migrate_leads.py --write --build
```

Run the local security guard before committing:

```bash
venv/bin/python scripts/security_check.py
```

Scan a new district without pushing:

```bash
venv/bin/python besiktas.py --query restoran --city "Istanbul Besiktas" --max 5
```

Scan, rebuild, commit, and push:

```bash
venv/bin/python besiktas.py --query restoran --city "Istanbul Besiktas" --max 5 --push
```

Serve the dashboard locally:

```bash
venv/bin/python -m http.server 8080 -d public
```

## Production Shape

`src/dashboard/template.html` is the source template. `public/index.html` is generated from it by embedding `leads_final.json` as base64 JSON.

Pipeline actions currently persist in browser `localStorage`; the dashboard can export that outreach state as JSON. The next production step is moving status and outreach events to SQLite or a hosted database.

## Security Reminder

Do not deploy or push new production changes until any API key that appeared in Git history has been rotated and `.env` has been purged from history. See `SECURITY.md`.
