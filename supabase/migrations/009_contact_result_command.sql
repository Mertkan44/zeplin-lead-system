-- Contact results recorded as one transaction, with real idempotency.
--
-- Safe to run repeatedly and safe for the previous application version: it only
-- adds a column, a table, triggers and functions. Apply it before deploying code
-- that calls record_contact_result.

-- CRM revision of a lead. The contact command bumps it; any other status change
-- (pipeline drag, /api/status) bumps it through the trigger.
alter table public.leads add column if not exists revision integer not null default 0;

create or replace function public.bump_lead_revision()
returns trigger
language plpgsql
set search_path = public
as $$
begin
  if new.status is distinct from old.status and new.revision = old.revision then
    new.revision := old.revision + 1;
  end if;
  return new;
end;
$$;

drop trigger if exists leads_bump_revision on public.leads;
create trigger leads_bump_revision
before update on public.leads
for each row execute function public.bump_lead_revision();

-- One row per logical submission. A retry with the same key gets the stored
-- response instead of running the command again; the same key with another
-- payload is rejected.
create table if not exists public.command_requests (
  idempotency_key text primary key,
  command text not null,
  actor_email text not null,
  request_hash text not null,
  response jsonb not null,
  created_at timestamptz not null default now()
);
create index if not exists command_requests_created_idx on public.command_requests (created_at);
alter table public.command_requests enable row level security;
grant select, insert, delete on public.command_requests to service_role;

-- Business rules (validation, default follow-up date, status per outcome) live
-- in src/activity.py; this function applies them atomically and re-checks
-- ownership inside the transaction. Errors use PostgREST's PTxxx codes so the
-- HTTP status is meaningful: PT400 bad input, PT403 not the owner, PT404 no
-- such lead, PT409 stale revision or reused idempotency key.
create or replace function public.record_contact_result(
  p_idempotency_key text,
  p_request_hash text,
  p_actor_email text,
  p_actor_is_admin boolean,
  p_lead_name text,
  p_expected_revision integer,
  p_channel text,
  p_outcome text,
  p_follow_up_at timestamptz,
  p_service_slugs text[],
  p_contact_name text,
  p_note text,
  p_lead_status text,
  p_assignment_status text
)
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
  previous public.command_requests;
  target public.leads;
  owner_row public.lead_assignments;
  new_event_id bigint;
  new_revision integer;
  happened timestamptz := now();
  assignment_due timestamptz;
  result jsonb;
begin
  if coalesce(length(p_idempotency_key), 0) < 16 or coalesce(p_request_hash, '') = '' then
    raise exception using errcode = 'PT400', message = 'IDEMPOTENCY_KEY_REQUIRED';
  end if;
  if p_assignment_status not in ('active', 'done') then
    raise exception using errcode = 'PT400', message = 'ASSIGNMENT_STATUS_INVALID';
  end if;

  -- Two concurrent submissions with one key run one after the other.
  perform pg_advisory_xact_lock(hashtext('record_contact_result:' || p_idempotency_key));
  select * into previous from public.command_requests where idempotency_key = p_idempotency_key;
  if found then
    if previous.command <> 'record_contact_result'
       or previous.request_hash <> p_request_hash
       or lower(previous.actor_email) <> lower(p_actor_email) then
      raise exception using errcode = 'PT409', message = 'IDEMPOTENCY_KEY_REUSED';
    end if;
    return previous.response || jsonb_build_object('replayed', true);
  end if;

  select * into target from public.leads where name = p_lead_name for update;
  if not found then
    raise exception using errcode = 'PT404', message = 'LEAD_NOT_FOUND';
  end if;

  select * into owner_row
  from public.lead_assignments
  where lead_name = target.name and status = 'active'
  for update;
  if not p_actor_is_admin and (owner_row.id is null or lower(owner_row.user_email) <> lower(p_actor_email)) then
    raise exception using errcode = 'PT403', message = 'LEAD_NOT_ASSIGNED';
  end if;

  if p_expected_revision is not null and p_expected_revision <> target.revision then
    raise exception using errcode = 'PT409', message = 'LEAD_VERSION_CONFLICT';
  end if;

  insert into public.outreach_events (
    lead_name, lead_id, action, note, happened_at, actor_email, source, idempotency_key,
    channel, outcome, follow_up_at, service_slugs, contact_name
  )
  values (
    target.name, target.id, 'contact_result_recorded', p_note, happened, lower(p_actor_email),
    'dashboard', p_idempotency_key, p_channel, p_outcome, p_follow_up_at,
    coalesce(p_service_slugs, '{}'), p_contact_name
  )
  returning id into new_event_id;

  update public.leads
  set status = p_lead_status, revision = revision + 1, updated_at = happened
  where id = target.id
  returning revision into new_revision;

  -- Closing the lead closes its follow-up; otherwise the owner gets the new date.
  assignment_due := case when p_assignment_status = 'done' then null else p_follow_up_at end;
  if owner_row.id is not null then
    update public.lead_assignments
    set status = p_assignment_status,
        due_at = assignment_due,
        updated_at = happened,
        meta = coalesce(meta, '{}'::jsonb) || jsonb_build_object(
          'last_outcome', p_outcome,
          'last_channel', p_channel,
          'last_contact_at', happened,
          'follow_up_at', assignment_due,
          'service_slugs', to_jsonb(coalesce(p_service_slugs, '{}')),
          'needs_verification', case when p_outcome = 'wrong_number' then 'phone' end
        )
    where id = owner_row.id;
  end if;

  insert into public.audit_events (actor_email, event_type, target_type, target_key, meta)
  values (
    lower(p_actor_email), 'contact_result_recorded', 'lead', target.name,
    jsonb_build_object('event_id', new_event_id, 'outcome', p_outcome, 'revision', new_revision)
  );

  result := jsonb_build_object(
    'event_id', new_event_id,
    'lead_name', target.name,
    'lead_status', p_lead_status,
    'lead_revision', new_revision,
    'assignment_id', owner_row.id,
    'assignment_status', case when owner_row.id is null then null else p_assignment_status end,
    'follow_up_at', assignment_due,
    'happened_at', happened,
    'actor_email', lower(p_actor_email)
  );
  insert into public.command_requests (idempotency_key, command, actor_email, request_hash, response)
  values (p_idempotency_key, 'record_contact_result', lower(p_actor_email), p_request_hash, result);
  return result || jsonb_build_object('replayed', false);
end;
$$;
revoke all on function public.record_contact_result(text, text, text, boolean, text, integer, text, text, timestamptz, text[], text, text, text, text)
  from public, anon, authenticated;
grant execute on function public.record_contact_result(text, text, text, boolean, text, integer, text, text, timestamptz, text[], text, text, text, text)
  to service_role;

-- Readiness now also requires the contact command.
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
      'record_contact_result', to_regprocedure('public.record_contact_result(text,text,text,boolean,text,integer,text,text,timestamptz,text[],text,text,text,text)') is not null,
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
      'lead_revision', exists (
        select 1 from information_schema.columns
        where table_schema = 'public' and table_name = 'leads' and column_name = 'revision'
      ),
      'lead_sources', to_regclass('public.lead_sources') is not null
    )
  );
$$;
revoke all on function public.schema_readiness() from public, anon, authenticated;
grant execute on function public.schema_readiness() to service_role;

insert into public.schema_migrations (version) values ('009') on conflict do nothing;
