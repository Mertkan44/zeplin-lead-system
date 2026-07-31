-- Optional native columns for structured contact results.
-- The application is backward compatible and also reads versioned JSON notes,
-- so this migration can be applied without downtime.

alter table public.outreach_events
  add column if not exists channel text,
  add column if not exists outcome text,
  add column if not exists follow_up_at timestamptz,
  add column if not exists service_slugs text[] not null default '{}',
  add column if not exists contact_name text;

create index if not exists outreach_events_follow_up_idx
  on public.outreach_events (follow_up_at)
  where follow_up_at is not null;

create index if not exists outreach_events_outcome_idx
  on public.outreach_events (outcome, happened_at desc)
  where outcome is not null;
