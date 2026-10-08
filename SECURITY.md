# Security Notes

This repository is **public**. Code may live here; secrets and real lead data may not.

## Secrets

- `.env` and its variants are ignored; `scripts/security_check.py` (run in CI) fails
  on tracked env files and on common API-key patterns.
- A full scan of all 90 commits reachable on 2026-10-07 found no API key values in
  history: only the `your_...` placeholders in `.env.example`, and no committed `.env`.
- An earlier note recorded that a Groq key had been committed in early history. It is
  not in today's history, but it was public at some point and may survive in clones,
  forks or caches. **Rotate it in the Groq dashboard** if that has not been done, and
  keep the new key only in `.env` / Vercel / GitHub Actions secrets.

## Lead data

- Real lead data (business names, phones, addresses, research, CRM state) lives only
  in Supabase. Export a local working copy with `python scripts/export_leads.py`; the
  output is ignored by Git.
- `leads_final.json`, `leads_raw.json`, `leads_audited.json` and `outreach_log.json`
  were removed from the tree on 2026-10-07. They remain in **past commits**
  (`leads_final.json` in 17 commits since 2026-05-01), which anyone can still read
  while the repository is public.
- CI fails if `leads_*.json` or `outreach_log*.json` is tracked again, except the
  synthetic `tests/fixtures/leads_sample.json` (invented businesses only).

## Owner decisions still open

1. **Make the repository private** (GitHub → Settings → General → Danger Zone →
   Change visibility). The quickest way to stop further exposure of the old commits.
   It does not recall copies already downloaded.
2. **Optionally purge the old data and history** with `git filter-repo`, followed by a
   coordinated force-push, after a backup and after telling every collaborator. Do
   this as a separate maintenance step; nothing here force-pushes automatically.
3. **Rotate the old Groq key** as above.
