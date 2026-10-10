# Zeplin Lead System

Lead intelligence panel for Zeplin Media. It scrapes local businesses from Google Maps, audits their digital presence, matches Zeplin services, generates sales notes, and serves a role-aware CRM workspace.

## Setup

```bash
python3 -m venv venv
venv/bin/pip install -r requirements.txt
cp .env.example .env
venv/bin/playwright install chromium
```

Add `DEEPSEEK_API_KEY` to `.env` for AI report generation. The production
provider is `AI_PROVIDER=deepseek`; Groq remains an optional alternative.
DeepSeek defaults to `deepseek-v4-pro`, with thinking disabled for short sales
reports so the response budget is reserved for the final text.
The pipeline uses an AI cost mode: lower-priority leads use `DEEPSEEK_FLASH_MODEL`
and high-priority leads use `DEEPSEEK_PRO_MODEL`. Unchanged input never pays twice:
see "AI generations and costs" below.

Database schema lives in `supabase/migrations/` (001 … latest), the only
hand-edited source. Every migration is idempotent.

- **Fresh project:** run `supabase/schema.sql` once in the Supabase SQL editor. It is
  generated from the migrations (`python scripts/build_schema.py`); do not edit it.
- **Existing project:** run each migration you have not applied yet, in order.
  Re-running one that is already applied is safe. Older projects bootstrapped with
  the removed `apply_live_schema.sql` are covered by migrations 003–005.

The current code requires migration 011. Always apply new migrations before
deploying the code that needs them; every migration also works with the previous
code version.

Migration 011 ties AI generations to their input and records every provider call;
see "AI generations and costs". It removes nothing, so it can be applied through the
Supabase connector.

Migration 010 moves reads into the database: `readable_leads` holds the access rule,
`lead_activity_state` keeps each lead's latest contact result and manual verification
(updated by a trigger on `outreach_events`, rebuilt with `rebuild_lead_activity_state()`),
and `list_leads` serves the paginated lead list. No read path is capped at "the first
1,000 leads" or "the last 1,000 events" any more. Migration 010 contains no DROP or
DELETE statements, so it can be applied through the Supabase connector.

Migration 009 records a contact result in one transaction (`record_contact_result`):
the event, the lead status, the owner's follow-up date and an audit event are
written together or not at all, ownership is re-checked inside the transaction, a
stale form (lead `revision` changed meanwhile) gets 409, and the idempotency key
(one UUID per submission) makes retries return the first answer instead of writing
again. Won and lost results close the open follow-up; a wrong number sends the
lead back to verification. Default follow-up dates come from `FOLLOW_UP_DELAYS` in
`src/activity.py` for both the API and the dashboard.

Migration 008 repairs idempotent outreach
writes (databases built from migrations rejected every `on_conflict=idempotency_key`
insert), adds stable `lead_id` columns and `lead_sources` (Google place ids) next to
the name-based keys, and records the schema version. Check a deployment with
`GET /api/health`: it answers 200 when the schema is ready and 503 otherwise; admins
also see the version and any failed checks, and the admin workspace shows a banner.

Before relying on lead ids, review the identity dry run (read-only):

```bash
venv/bin/python scripts/lead_identity_report.py                 # live Supabase
venv/bin/python scripts/lead_identity_report.py --file leads_final.json
```

It lists leads that share a Google place id, phone or website, place ids already
recorded for another lead, and rows still missing `lead_id`. Nothing is merged
automatically. Reviewed merges are one-off SQL files in `supabase/data_fixes/`
(run once in the SQL editor; each is atomic and refuses to run twice).

CI proves that a fresh install and an upgrade from every historical `schema.sql`
end in the same schema, then runs `tests/sql/` behaviour checks. Locally, with any
throwaway PostgreSQL server:

```bash
python scripts/schema_parity.py --dsn postgresql://postgres@localhost:5432/postgres
```

Set `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, and a long random
`SESSION_SECRET` in Vercel. Team members log in with their individual Supabase
`app_users` account. The old shared admin password is disabled unless
`ALLOW_LEGACY_ADMIN_LOGIN=1` is deliberately set during a short migration window.

## AI generations and costs

- **Key:** a generation is identified by task, provider, requested model, a hash of
  the exact system + user prompt (so any change to the data the model sees), the
  prompt version and the service-catalog version. Places lookup bookkeeping (refresh
  times, attempts) is left out, so a refresh that finds the same data is free.
- **One paid call per input:** `ai_generations` is the cache and the lock
  (`claim_ai_generation`). A second request for an input being generated waits for
  the first one's text; past ~25 s the API answers 409 ("being prepared"). A failed
  or expired generation is taken over by the next request. The local
  `.cache/ai_generations.json` is only an extra copy for the worker and CLI (off on
  Vercel or with `AI_LOCAL_CACHE=0`); failing to write it never blocks the remote record.
- **Report state:** leads store `ai_input_hash`; the workspace and detail mark a
  report `current`, `stale` (the data changed since) or `unknown` (generated before
  hashes were stored). A stale report stays readable but is never shown as current,
  and the next action becomes "Raporu yenile". `/api/lead_ai` no longer trusts the
  prompt version alone; unchanged input is answered from the cache for free.
- **Ledger:** every provider request writes one `ai_token_ledger` row (`kind=usage`)
  with task, requested and actual model, outcome (`success`, `empty`, `error`,
  `cache_hit`), prompt / cached / completion tokens, cost and the rates applied, plus
  the job, actor and lead it was for. Empty answers, failures and fallbacks are
  recorded too. A search job's `reservation` is closed by a `release` row when the job
  ends, so open reservations and historical estimates are reported apart.
  `ai_spend_summary()` totals the whole ledger in the database.
- **Prices:** `ai_model_rates` (provider, model, start date, input / cached input /
  output USD per million tokens). Enter rows from the provider's official price list;
  without a row DeepSeek falls back to `DEEPSEEK_*_USD_PER_M_TOKENS`, other providers
  stay unpriced (counted as `unpriced_calls`, never guessed). The panel's job estimate
  comes from the API and is the same figure the job reserves.
- **Budget (optional):** set `AI_DAILY_BUDGET_USD` to refuse new paid calls once
  today's spend (Istanbul day) reaches it; cache hits still work. Unset means no cap.

## Lead data stays out of Git

This repository is public. Real lead data (businesses, contact details, research,
CRM state) lives only in Supabase. `leads_*.json` and `outreach_log.json` are
ignored, and `scripts/security_check.py` (run in CI) fails if one gets tracked.
Tests, CI and demos use the synthetic `tests/fixtures/leads_sample.json`
(regenerate with `python scripts/make_sample_leads.py`).

For the local CLI tools, export a working copy first:

```bash
venv/bin/python scripts/export_leads.py      # Supabase -> leads_final.json (local only)
```

## Common Commands

Normalize the local lead export:

```bash
venv/bin/python scripts/migrate_leads.py --write
```

Validate lead data (your local export, or the synthetic sample as CI does):

```bash
venv/bin/python scripts/validate_data.py
venv/bin/python scripts/validate_data.py tests/fixtures/leads_sample.json
```

Run the local security guard before committing:

```bash
venv/bin/python scripts/security_check.py
```

Scan a new district without pushing:

```bash
venv/bin/python besiktas.py --query restoran --city "Istanbul Besiktas" --max 5
```

Scan and sync the merged lead set to Supabase:

```bash
venv/bin/python besiktas.py --query restoran --city "Istanbul Besiktas" --max 5 --resume --deep-research --sync-supabase
```

Sync the current local `leads_final.json` (never committed) to Supabase:

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
GET /api/workspace                 # role-shaped dashboard payload (events: last 30 days, feed capped at 1,000)
GET /api/workspace?view=metrics&period=7|30|90|all   # report numbers with definitions (src/metrics.py)
GET /api/leads                     # paginated list: ?cursor=&limit=1-100&q=&status= -> {items, next_cursor, total}
GET /api/leads?id=123 | ?name=...  # one lead with assignments and latest activity
GET /api/outreach?lead=...         # timeline, newest first: &before=<event id>&limit=1-200 -> {items, next_before}
GET /api/health                    # 200/503 on schema readiness (details for admins)
POST /api/place_refresh            # refresh one assigned lead from Places API (New)
GET /api/place_refresh             # CRON_SECRET-protected daily refresh batch
```

Google Maps ratings, review counts, phone numbers, addresses and website URLs can
be refreshed through Places API (New). Configure `GOOGLE_PLACES_API_KEY`,
`CRON_SECRET`, and optionally `PLACES_REFRESH_BATCH_SIZE` in Vercel. The daily
Hobby-plan cron refreshes only stale records in a small batch; Instagram and menu
checks remain manual because there is no equivalent reliable public data source.

Places matching (`src/integrations/google_places.py`) never lets a matching name
outweigh the location. A lead that already has a place id is refreshed by that id.
Otherwise every text-search candidate must pass a location gate (district and
province from the lead's Maps address, falling back to the scanned area): a
candidate in another province is rejected, a same-name candidate in another
district or two close branches become `ambiguous`, and a phone or website match is
extra evidence. Results are `verified`, `ambiguous` (the panel lists the candidates
and a person picks one), `not_matched` or `provider_error`. A failed or ambiguous
lookup never erases earlier verified data, and a place id already recorded for
another lead is reported as a likely duplicate instead of being copied.

Every reader uses one effective snapshot of a lead (`src/lead_facts.py`): the
workspace, the lead detail, the workflow stage, service matching and AI generation.
Each field (website, Instagram, phone, rating, reviews, Maps link, address, menu)
carries its value, source (`manual`, `google_places`, `scrape`), observation time,
who verified it, whether it is stale and what other sources say. A fresh manual
check wins and is never overwritten by a later scrape; audit findings about a
website or profile that is no longer the effective one stop counting as evidence,
and a manual "not found" is evidence of its own. Stale limits (`STALE_AFTER_DAYS`):
manual checks 90 days, Places 30 days, scrape 90 days. An expired manual check has
to be done again before the lead is ready to contact.

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

## Dashboard (web/)

The dashboard is a Vite + React + TypeScript app in `web/`, compiled ahead of time
into `public/` (committed; Vercel serves it next to the Python API). There is no
runtime JSX compilation and no third-party script: the CSP allows only same-origin
scripts plus the hash of the one inline theme snippet, and no inline styles (React
sets styles through the CSSOM, which `style-src` does not restrict). The browser
tests serve the page with the production CSP, so a violation fails CI.

```bash
python src/dashboard/build.py      # catalog + follow-up rules -> web/src/generated/app-config.json
npm ci --prefix web
npm --prefix web run build         # typecheck, then build into public/ (commit the result)
RUN_E2E=1 python -m unittest discover -s tests/e2e   # browser tests against public/
```

CI rebuilds `public/` and fails if it differs from what is committed, and runs the
browser tests. If you change the inline script in `web/index.html`, update its
`sha256` in the `script-src` of `vercel.json` (a unit test checks they match).

- `web/src/lib/api.ts` is the one HTTP client: same-origin cookies, JSON, a 401 ends
  the session, errors carry the API's status, `error` and `code`.
- `web/src/lib/router.ts` keeps the screen and the open lead in the URL
  (`/leads/<id>` by database id, `/pipeline`, `/profile`, ...), so deep links,
  back/forward and refresh keep the same lead.
- `web/src/lib/queryClient.ts` is the one data cache (TanStack Query). Server data
  lives there keyed by the signed-in user, never in module variables or
  localStorage; `web/src/data/` reads (`workspace.ts`) and writes (`mutations.ts`)
  it, `web/src/domain/` holds the shared rules (statuses, next action, pipeline
  stage).
- `web/src/ui/` holds the shared parts: `Button`, `Field`/`Input`/`Select`/`Textarea`,
  `Dialog`/`ConfirmDialog` (focus trap, Escape, focus return), `Badge`/`StatusBadge`,
  `EmptyState`/`ErrorState`/`Banner`. Colors and fonts are tokens in
  `web/src/styles/tokens.css` (dark and light); components use CSS modules.
- `web/src/app/` is the shell (login, navigation, search, routing). Navigation is a
  sidebar from 768 px (icons only below 1280 px) and, on phones, a top bar plus
  a bottom bar with a menu drawer; `/` opens the lead search. `web/src/screens/`
  holds one folder per screen (today, workspace, leads, lead, contact, pipeline,
  services, analytics, admin, profile), each a typed component with its CSS
  module. All dashboard code is TypeScript (a unit test keeps it that way).

After authentication the dashboard reads role-filtered live data from the API. CRM
data is kept in memory only; logout, a 401 response, or a user switch clears the
cache and cancels requests in flight. Only the theme is kept in localStorage.

Lead access follows one policy, `public.readable_leads` (migration 010), used by every
read path through `src/auth.py`: admins see every lead; a sales user reads and writes
leads with an active assignment, and keeps read-only access to leads they closed or
paused only while no one else owns them. An archived assignment (the lead was handed
over) grants nothing. Writes additionally re-check the active assignment.

Admin search runs as a queue-backed workflow. The Vercel API creates `admin_search_jobs`
and reserves estimated DeepSeek token usage in `ai_token_ledger`; a worker then runs
`scripts/process_search_jobs.py` to execute the scraping/audit/AI pipeline and sync
results back to Supabase. This avoids long Playwright browser jobs inside short-lived
Vercel request handlers.

The services matrix lives in `src/services.py`. Each service has a category,
delivery type, evidence rules, deliverables, exclusions, and discovery questions.
Only approved, evidence-backed services can be recommended automatically; the
system does not invent marketing package names or revenue estimates.
`scripts/migrate_leads.py` writes matched services and the primary service
recommendation into the local operational dataset. `src/dashboard/build.py`
reads no lead data; it writes only the non-secret service catalog and follow-up
rules for the dashboard build. Scans no longer rebuild or push anything: `--build`
and `--push` are accepted but do nothing.

## Report metrics

`src/metrics.py` defines every number on the Raporlar screen once (review §10):
days start at midnight Europe/Istanbul; activity counts use the date the
contact result was recorded, new leads use `leads.created_at` and analyses
`last_analyzed`; "won" counts distinct businesses, so a repeated win does not
inflate it; unknown scores are left out of averages instead of counted as 0;
sectors beyond the top five fold into "Diğer". There is no stage history yet,
so current statuses are shown as a distribution, not a conversion funnel.
`tests/test_metrics.py` checks the numerator and denominator of each metric.

## Security Reminder

See `SECURITY.md` for the secret and data history of this repository and the
remaining owner actions.

## Operations and release checks (WP15)

Read-only release smoke, hourly queue/AI monitoring, private PostgreSQL backups
and an empty-target restore rehearsal are described in [docs/operations.md](docs/operations.md).
Set the GitHub repository variable `PRODUCTION_URL` to the production origin.
The Operations workflow verifies the deployed commit after main CI; it never
starts paid work. CI also proves synthetic backup/restore, RLS/grant parity and
refusal of populated targets or damaged archives. Live backups need a separate
DB connection and protected storage; service-role HTTP access alone cannot create
one. Audit persistence failures produce a sanitized operational log without
turning a successful CRM mutation into a retry.
