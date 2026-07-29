# Zeplin Lead System

Lead intelligence panel for Zeplin Media. It scrapes local businesses from Google Maps, audits their digital presence, matches Zeplin services, generates sales notes, and serves a role-aware CRM workspace.

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

For a fresh Supabase project, run `supabase/schema.sql` in the SQL editor. For an
existing project, apply migrations in order through
`supabase/migrations/006_security_crm_hardening.sql`. The last migration adds stable
lead identities, atomic queue claims, assignment integrity, audit events, and
persistent AI generations.

Set `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, and a long random
`SESSION_SECRET` in Vercel. Team members log in with their individual Supabase
`app_users` account. The old shared admin password is disabled unless
`ALLOW_LEGACY_ADMIN_LOGIN=1` is deliberately set during a short migration window.

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

Create panel users in Supabase:

```bash
venv/bin/python scripts/create_user.py --email satis1@zeplinmedia.com --name "Satis 1" --role sales --password "temporary-password"
venv/bin/python scripts/create_user.py --email admin@zeplinmedia.com --name "Admin" --role admin --password "temporary-password"
```

Seed the default Zeplin team with a separate password for every member:

```bash
export TEAM_PASSWORD_ASLIHAN="..."
export TEAM_PASSWORD_AHU="..."
export TEAM_PASSWORD_MERTKAN="..."
export TEAM_PASSWORD_TURKER="..."
venv/bin/python scripts/seed_team_users.py
```

Role-ready backend endpoints:

```text
GET/POST/DELETE /api/auth
GET/POST/PATCH /api/users          # admin only
GET/POST/PATCH /api/assignments    # admin assigns, users update assignment status
GET /api/workspace                 # role-shaped dashboard payload
```

In production, `.github/workflows/process-search-jobs.yml` checks Supabase every
15 minutes and atomically claims up to three queued admin search jobs. Add these GitHub Actions
secrets before relying on the automatic worker:

```bash
SUPABASE_URL
SUPABASE_SERVICE_ROLE_KEY
DEEPSEEK_API_KEY
```

You can load those from local `.env` without printing secret values:

```bash
gh auth login
bash scripts/setup_github_actions_secrets.sh
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

Run the complete dashboard and API locally with the linked Vercel environment:

```bash
vercel env pull .env.local
vercel dev --listen 3000
```

Opening `public/index.html` alone only renders the login shell; authenticated CRM
data is intentionally available only through the API.

## Production Shape

`src/dashboard/template.html` is the source template. `public/index.html` is
generated without embedding CRM lead records. After authentication, the dashboard
reads role-filtered live data from Vercel API routes backed by Supabase.

Admin search runs as a queue-backed workflow. The Vercel API creates `admin_search_jobs`
and reserves estimated DeepSeek token usage in `ai_token_ledger`; a worker then runs
`scripts/process_search_jobs.py` to execute the scraping/audit/AI pipeline and sync
results back to Supabase. This avoids long Playwright browser jobs inside short-lived
Vercel request handlers.

The services matrix lives in `src/services.py`. Each service has a category, owner,
sales angle, detectable signals, pricing range, and trigger list.
`scripts/migrate_leads.py` writes matched services and recommended packages into
the local operational dataset. `src/dashboard/build.py` embeds only the non-secret
service catalog into the static shell.

## Security Reminder

Any API key that appeared in Git history must be rotated. Purging shared history
requires a coordinated force push and should be handled as a separate maintenance
window. See `SECURITY.md`.
