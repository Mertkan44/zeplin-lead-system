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
To use DeepSeek instead, set `AI_PROVIDER=deepseek` and add `DEEPSEEK_API_KEY`.
DeepSeek defaults to `deepseek-v4-pro`.
The pipeline uses an AI cost mode: lower-priority leads use `DEEPSEEK_FLASH_MODEL`
and high-priority leads use `DEEPSEEK_PRO_MODEL`. AI generations are cached in
`.cache/ai_generations.json` so unchanged leads do not burn tokens repeatedly.

For Supabase persistence on the free plan, create a project, run `supabase/schema.sql`
in the SQL editor, then add `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` to `.env`.
For admin login and production search jobs, also set `ADMIN_PASSWORD` and
`SESSION_SECRET` in Vercel Environment Variables.

## Common Commands

Normalize existing leads and rebuild the dashboard:

```bash
venv/bin/python scripts/migrate_leads.py --write --build
```

Validate lead data before publishing:

```bash
venv/bin/python scripts/validate_data.py
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

Scan and sync the merged lead set to Supabase:

```bash
venv/bin/python besiktas.py --query restoran --city "Istanbul Besiktas" --max 5 --resume --deep-research --sync-supabase
```

Sync the current local `leads_final.json` to Supabase:

```bash
venv/bin/python scripts/sync_supabase.py
```

Process queued admin search jobs:

```bash
venv/bin/python scripts/process_search_jobs.py --limit 1
```

In production, `.github/workflows/process-search-jobs.yml` checks Supabase every
30 minutes and processes one queued admin search job. Add these GitHub Actions
secrets before relying on the automatic worker:

```bash
SUPABASE_URL
SUPABASE_SERVICE_ROLE_KEY
DEEPSEEK_API_KEY
```

Use the technical CLI for modular operations:

```bash
venv/bin/python scripts/zeplin.py validate
venv/bin/python scripts/zeplin.py research --limit 5
venv/bin/python scripts/zeplin.py ai --limit 5
venv/bin/python scripts/zeplin.py sync
venv/bin/python scripts/zeplin.py leads --limit 10
venv/bin/python scripts/zeplin.py cache
```

Serve the dashboard locally:

```bash
venv/bin/python -m http.server 8080 -d public
```

## Production Shape

`src/dashboard/template.html` is the source template. `public/index.html` is generated from it by embedding `leads_final.json` as base64 JSON. In production, the dashboard reads live data from Vercel API routes backed by Supabase.

Admin search runs as a queue-backed workflow. The Vercel API creates `admin_search_jobs`
and reserves estimated DeepSeek token usage in `ai_token_ledger`; a worker then runs
`scripts/process_search_jobs.py` to execute the scraping/audit/AI pipeline and sync
results back to Supabase. This avoids long Playwright browser jobs inside short-lived
Vercel request handlers.

The services matrix lives in `src/services.py`. Each service has a category, owner, sales angle, detectable signals, pricing range, and trigger list. `scripts/migrate_leads.py` writes the matched services plus the recommended package into `leads_final.json`, then `src/dashboard/build.py` embeds both leads and the full service catalog into the static dashboard.

## Security Reminder

Do not deploy or push new production changes until any API key that appeared in Git history has been rotated and `.env` has been purged from history. See `SECURITY.md`.
