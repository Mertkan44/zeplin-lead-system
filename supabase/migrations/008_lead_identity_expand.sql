-- Stable lead identity (expand phase), idempotency repair and schema readiness.
--
-- Safe to run repeatedly. Nothing here removes the name-based columns or the
-- unique(name) constraint: the application keeps reading and writing lead_name,
-- and triggers keep the new lead_id columns in step. Contract steps (NOT NULL,
-- dropping unique(name)) come in a later migration once the app uses lead_id.

create table if not exists public.schema_migrations (
  version text primary key,
  applied_at timestamptz not null default now()
);
alter table public.schema_migrations enable row level security;
grant select on public.schema_migrations to service_role;

-- The original tables only got service_role grants from later schema.sql
-- snapshots, never from a migration. Make every path end up the same.
grant select, insert, update, delete on public.leads to service_role;
grant select, insert, update, delete on public.outreach_events to service_role;
grant select, insert, update, delete on public.pipeline_runs to service_role;
grant usage, select on sequence public.leads_id_seq to service_role;
grant usage, select on sequence public.outreach_events_id_seq to service_role;
grant usage, select on sequence public.pipeline_runs_id_seq to service_role;

-- PostgREST sends `ON CONFLICT (idempotency_key)`. Postgres cannot infer the
-- partial unique index from migration 006 for that clause, so databases built
-- from migrations rejected every idempotent insert. A plain unique constraint
-- (NULLs stay allowed) works on every path.
do $$
begin
  if not exists (
    select 1 from pg_constraint
    where conrelid = 'public.outreach_events'::regclass
      and conname = 'outreach_events_idempotency_key_key'
  ) then
    alter table public.outreach_events
      add constraint outreach_events_idempotency_key_key unique (idempotency_key);
  end if;
  if not exists (
    select 1 from pg_constraint
    where conrelid = 'public.leads'::regclass
      and conname = 'leads_external_id_key'
  ) then
    alter table public.leads add constraint leads_external_id_key unique (external_id);
  end if;
end $$;
drop index if exists public.outreach_events_idempotency_uidx;
drop index if exists public.leads_external_id_uidx;

-- Renaming a lead must not break its history. Recreate the name foreign keys
-- with ON UPDATE CASCADE (they already cascade on delete).
do $$
begin
  if exists (
    select 1 from pg_constraint
    where conname = 'outreach_events_lead_name_fkey' and confupdtype <> 'c'
  ) then
    alter table public.outreach_events drop constraint outreach_events_lead_name_fkey;
  end if;
  if not exists (select 1 from pg_constraint where conname = 'outreach_events_lead_name_fkey') then
    alter table public.outreach_events
      add constraint outreach_events_lead_name_fkey foreign key (lead_name)
      references public.leads(name) on update cascade on delete cascade;
  end if;
  if exists (
    select 1 from pg_constraint
    where conname = 'lead_assignments_lead_name_fkey' and confupdtype <> 'c'
  ) then
    alter table public.lead_assignments drop constraint lead_assignments_lead_name_fkey;
  end if;
  if not exists (select 1 from pg_constraint where conname = 'lead_assignments_lead_name_fkey') then
    alter table public.lead_assignments
      add constraint lead_assignments_lead_name_fkey foreign key (lead_name)
      references public.leads(name) on update cascade on delete cascade;
  end if;
end $$;

-- lead_id: the identity that survives renames and same-name branches.
alter table public.outreach_events add column if not exists lead_id bigint;
alter table public.lead_assignments add column if not exists lead_id bigint;

do $$
begin
  if not exists (select 1 from pg_constraint where conname = 'outreach_events_lead_id_fkey') then
    alter table public.outreach_events
      add constraint outreach_events_lead_id_fkey foreign key (lead_id)
      references public.leads(id) on delete cascade;
  end if;
  if not exists (select 1 from pg_constraint where conname = 'lead_assignments_lead_id_fkey') then
    alter table public.lead_assignments
      add constraint lead_assignments_lead_id_fkey foreign key (lead_id)
      references public.leads(id) on delete cascade;
  end if;
end $$;

update public.outreach_events event
set lead_id = lead.id
from public.leads lead
where event.lead_id is null and lead.name = event.lead_name;

update public.lead_assignments assignment
set lead_id = lead.id
from public.leads lead
where assignment.lead_id is null and lead.name = assignment.lead_name;

create index if not exists outreach_events_lead_id_idx
  on public.outreach_events (lead_id, happened_at desc);
create index if not exists lead_assignments_lead_id_idx
  on public.lead_assignments (lead_id, status);

-- While the application writes lead_name only, derive lead_id from it.
create or replace function public.fill_lead_id_from_name()
returns trigger
language plpgsql
set search_path = public
as $$
begin
  if new.lead_name is not null and (
    (tg_op = 'INSERT' and new.lead_id is null)
    or (tg_op = 'UPDATE' and new.lead_name is distinct from old.lead_name and new.lead_id is not distinct from old.lead_id)
  ) then
    select id into new.lead_id from public.leads where name = new.lead_name;
  end if;
  return new;
end;
$$;

drop trigger if exists outreach_events_fill_lead_id on public.outreach_events;
create trigger outreach_events_fill_lead_id
before insert or update on public.outreach_events
for each row execute function public.fill_lead_id_from_name();

drop trigger if exists lead_assignments_fill_lead_id on public.lead_assignments;
create trigger lead_assignments_fill_lead_id
before insert or update on public.lead_assignments
for each row execute function public.fill_lead_id_from_name();

-- External identities. A provider id belongs to exactly one lead.
create table if not exists public.lead_sources (
  id bigint generated by default as identity primary key,
  lead_id bigint not null references public.leads(id) on delete cascade,
  provider text not null check (provider in ('google_places')),
  provider_id text not null,
  url text,
  first_seen_at timestamptz not null default now(),
  last_seen_at timestamptz not null default now(),
  unique (provider, provider_id)
);
create index if not exists lead_sources_lead_idx on public.lead_sources (lead_id);
alter table public.lead_sources enable row level security;
grant select, insert, update, delete on public.lead_sources to service_role;
grant usage, select on sequence public.lead_sources_id_seq to service_role;

-- Google place id: the verified Places API result first, else the id embedded
-- in a Google Maps URL (".../data=...!19sChIJ...").
create or replace function public.lead_google_place_id(maps_url text, raw jsonb)
returns text
language sql
immutable
set search_path = public
as $$
  select coalesce(
    case
      when raw #>> '{research,google_places,status}' = 'verified'
        then nullif(raw #>> '{research,google_places,place_id}', '')
    end,
    substring(coalesce(maps_url, raw ->> 'maps_url', '') from '!19s([A-Za-z0-9_-]{10,})')
  );
$$;

-- Record the provider id when a lead is written. If the id already belongs to
-- another lead, nothing is merged: scripts/lead_identity_report.py lists it.
create or replace function public.record_lead_source()
returns trigger
language plpgsql
set search_path = public
as $$
declare
  place_id text := public.lead_google_place_id(new.maps_url, new.raw);
begin
  if place_id is not null then
    insert into public.lead_sources (lead_id, provider, provider_id, url)
    values (new.id, 'google_places', place_id, new.maps_url)
    on conflict (provider, provider_id) do update
      set last_seen_at = now(), url = coalesce(excluded.url, lead_sources.url)
      where lead_sources.lead_id = excluded.lead_id;
  end if;
  return new;
end;
$$;

drop trigger if exists leads_record_source on public.leads;
create trigger leads_record_source
after insert or update of maps_url, raw on public.leads
for each row execute function public.record_lead_source();

-- Backfill only unambiguous ids; shared ids are left for manual review.
insert into public.lead_sources (lead_id, provider, provider_id, url)
select min(lead.id), 'google_places', candidate.place_id, min(lead.maps_url)
from public.leads lead
cross join lateral (select public.lead_google_place_id(lead.maps_url, lead.raw) as place_id) candidate
where candidate.place_id is not null
group by candidate.place_id
having count(*) = 1
on conflict (provider, provider_id) do nothing;

-- One call that tells the API whether this database can serve it.
create or replace function public.schema_readiness()
returns jsonb
language sql
stable
security definer
set search_path = public
as $$
  select jsonb_build_object(
    'version', (select max(version) from public.schema_migrations),
    'checks', jsonb_build_object(
      'assign_lead_owner', to_regprocedure('public.assign_lead_owner(text,text,timestamptz,text,text,jsonb)') is not null,
      'claim_admin_search_jobs', to_regprocedure('public.claim_admin_search_jobs(integer)') is not null,
      'create_admin_search_job', to_regprocedure('public.create_admin_search_job(text,text,integer,boolean,text,text,integer,numeric,jsonb)') is not null,
      'check_login_rate_limit', to_regprocedure('public.check_login_rate_limit(text,integer,integer)') is not null,
      'record_login_attempt', to_regprocedure('public.record_login_attempt(text,boolean)') is not null,
      'one_active_owner_index', to_regclass('public.lead_assignments_one_active_owner_uidx') is not null,
      'idempotency_constraint', exists (
        select 1 from pg_constraint
        where conrelid = 'public.outreach_events'::regclass
          and conname = 'outreach_events_idempotency_key_key'
      ),
      'structured_outreach_columns', exists (
        select 1 from information_schema.columns
        where table_schema = 'public' and table_name = 'outreach_events' and column_name = 'follow_up_at'
      ),
      'lead_id_columns', exists (
        select 1 from information_schema.columns
        where table_schema = 'public' and table_name = 'lead_assignments' and column_name = 'lead_id'
      ),
      'lead_sources', to_regclass('public.lead_sources') is not null
    )
  );
$$;
revoke all on function public.schema_readiness() from public, anon, authenticated;
grant execute on function public.schema_readiness() to service_role;

insert into public.schema_migrations (version) values ('008') on conflict do nothing;
