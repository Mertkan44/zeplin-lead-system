-- Scoped reads: the access policy, the current activity state of a lead and the
-- paginated lead list all run inside the database.
--
-- Safe to run repeatedly and safe for the previous application version: it only
-- adds a table, triggers and functions. (No statement here removes anything,
-- so it can be applied through the Supabase connector without a confirmation.)

-- Who may read which lead. Same rule as before, now in one place:
--   * an active assignment gives read and write access;
--   * a done or snoozed assignment gives read access while nobody else holds
--     the lead's active assignment;
--   * an archived assignment (the lead was handed over) gives nothing.
-- Admins read every lead and do not call this.
create or replace function public.readable_leads(p_email text)
returns table (lead_id bigint, lead_name text, can_write boolean)
language sql
stable
security definer
set search_path = public
as $$
  select lead.id, lead.name, assignment.status = 'active'
  from public.lead_assignments assignment
  join public.leads lead on lead.name = assignment.lead_name
  where lower(assignment.user_email) = lower(p_email)
    and (
      assignment.status = 'active'
      or (
        assignment.status in ('done', 'snoozed')
        and not exists (
          select 1 from public.lead_assignments other
          where other.lead_name = assignment.lead_name
            and other.status = 'active'
            and lower(other.user_email) <> lower(p_email)
        )
      )
    );
$$;
revoke all on function public.readable_leads(text) from public, anon, authenticated;
grant execute on function public.readable_leads(text) to service_role;

-- Current activity of each lead, kept in step with outreach_events. The event
-- log stays append-only; this projection answers "latest contact result" and
-- "latest manual verification" without scanning the log, however long it gets.
create table if not exists public.lead_activity_state (
  lead_id bigint primary key references public.leads(id) on delete cascade,
  latest_contact jsonb,
  latest_contact_at timestamptz,
  latest_contact_actor text,
  latest_outcome text,
  latest_follow_up_at timestamptz,
  contact_result_count integer not null default 0,
  latest_manual_verification jsonb,
  latest_manual_verification_at timestamptz,
  updated_at timestamptz not null default now()
);
create index if not exists lead_activity_state_follow_up_idx
  on public.lead_activity_state (latest_follow_up_at)
  where latest_follow_up_at is not null;
alter table public.lead_activity_state enable row level security;
grant select, insert, update on public.lead_activity_state to service_role;

-- Migration 008's version left lead_id empty when an update cleared it while
-- changing lead_name. Fill it whenever it is empty, and follow a rename when the
-- caller did not set lead_id itself.
create or replace function public.fill_lead_id_from_name()
returns trigger
language plpgsql
set search_path = public
as $$
begin
  if new.lead_name is not null and (
    new.lead_id is null
    or (tg_op = 'UPDATE' and new.lead_name is distinct from old.lead_name and new.lead_id is not distinct from old.lead_id)
  ) then
    select id into new.lead_id from public.leads where name = new.lead_name;
  end if;
  return new;
end;
$$;

create index if not exists outreach_events_lead_action_idx
  on public.outreach_events (lead_id, action, happened_at desc, id desc);

-- Notes written before migration 007 carry the contact result as
-- "ZEPLIN_ACTIVITY_V1:{json}". Decode defensively: a malformed note yields
-- null instead of failing the write that triggered the refresh.
create or replace function public.activity_note_json(note text)
returns jsonb
language plpgsql
immutable
set search_path = public
as $$
begin
  if note like 'ZEPLIN_ACTIVITY_V1:%' then
    return substr(note, length('ZEPLIN_ACTIVITY_V1:') + 1)::jsonb;
  end if;
  return null;
exception when others then
  return null;
end;
$$;

create or replace function public.safe_timestamptz(value text)
returns timestamptz
language plpgsql
immutable
set search_path = public
as $$
begin
  return value::timestamptz;
exception when others then
  return null;
end;
$$;

create or replace function public.refresh_lead_activity_state(p_lead_id bigint)
returns void
language plpgsql
security definer
set search_path = public
as $$
declare
  contact public.outreach_events;
  manual public.outreach_events;
  contact_total integer;
  decoded jsonb;
begin
  if p_lead_id is null or not exists (select 1 from public.leads where id = p_lead_id) then
    return;
  end if;
  select * into contact from public.outreach_events
  where lead_id = p_lead_id and action = 'contact_result_recorded'
  order by happened_at desc, id desc limit 1;
  select * into manual from public.outreach_events
  where lead_id = p_lead_id and action = 'manual_verification_saved'
  order by happened_at desc, id desc limit 1;
  select count(*) into contact_total from public.outreach_events
  where lead_id = p_lead_id and action = 'contact_result_recorded';
  decoded := public.activity_note_json(contact.note);

  insert into public.lead_activity_state as state (
    lead_id, latest_contact, latest_contact_at, latest_contact_actor, latest_outcome,
    latest_follow_up_at, contact_result_count, latest_manual_verification,
    latest_manual_verification_at, updated_at
  )
  values (
    p_lead_id,
    case when contact.id is null then null else to_jsonb(contact) end,
    contact.happened_at,
    lower(contact.actor_email),
    coalesce(contact.outcome, decoded ->> 'outcome'),
    coalesce(contact.follow_up_at, public.safe_timestamptz(decoded ->> 'follow_up_at')),
    contact_total,
    case when manual.id is null then null else to_jsonb(manual) end,
    manual.happened_at,
    now()
  )
  on conflict (lead_id) do update set
    latest_contact = excluded.latest_contact,
    latest_contact_at = excluded.latest_contact_at,
    latest_contact_actor = excluded.latest_contact_actor,
    latest_outcome = excluded.latest_outcome,
    latest_follow_up_at = excluded.latest_follow_up_at,
    contact_result_count = excluded.contact_result_count,
    latest_manual_verification = excluded.latest_manual_verification,
    latest_manual_verification_at = excluded.latest_manual_verification_at,
    updated_at = excluded.updated_at;
end;
$$;
revoke all on function public.refresh_lead_activity_state(bigint) from public, anon, authenticated;
grant execute on function public.refresh_lead_activity_state(bigint) to service_role;

create or replace function public.outreach_events_refresh_state()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
  perform public.refresh_lead_activity_state(new.lead_id);
  if tg_op = 'UPDATE' and old.lead_id is distinct from new.lead_id then
    perform public.refresh_lead_activity_state(old.lead_id);
  end if;
  return null;
end;
$$;

-- Runs after fill_lead_id_from_name (a BEFORE trigger), so new.lead_id is set.
create or replace trigger outreach_events_refresh_state
after insert or update on public.outreach_events
for each row execute function public.outreach_events_refresh_state();

-- Rebuild every row from the event log, e.g. after bulk changes to events.
-- Leads whose events are all gone get an empty state row.
create or replace function public.rebuild_lead_activity_state()
returns integer
language plpgsql
security definer
set search_path = public
as $$
declare
  target bigint;
  refreshed integer := 0;
begin
  for target in
    select lead_id from public.lead_activity_state
    union
    select distinct lead_id from public.outreach_events where lead_id is not null
  loop
    perform public.refresh_lead_activity_state(target);
    refreshed := refreshed + 1;
  end loop;
  return refreshed;
end;
$$;
revoke all on function public.rebuild_lead_activity_state() from public, anon, authenticated;
grant execute on function public.rebuild_lead_activity_state() to service_role;

select public.rebuild_lead_activity_state();

-- Paginated lead list with a minimal row per lead. Order: commercial priority
-- (highest first, unknown last), then id; the cursor is the last row's
-- (priority, id). total counts the whole readable scope after filters.
create or replace function public.list_leads(
  p_actor_email text,
  p_is_admin boolean,
  p_after_priority integer,
  p_after_id bigint,
  p_limit integer,
  p_search text,
  p_status text
)
returns jsonb
language plpgsql
stable
security definer
set search_path = public
as $$
declare
  page_size integer := least(greatest(coalesce(p_limit, 50), 1), 100);
  pattern text := case
    when coalesce(trim(p_search), '') = '' then null
    else '%' || replace(replace(replace(trim(p_search), '\', '\\'), '%', '\%'), '_', '\_') || '%'
  end;
  rows jsonb;
  total integer;
  last_row jsonb;
begin
  with scope as (
    select lead.*
    from public.leads lead
    where (p_is_admin or lead.id in (select lead_id from public.readable_leads(p_actor_email)))
      and (pattern is null or lead.name ilike pattern or lead.city ilike pattern or lead.sector ilike pattern)
      and (p_status is null or lead.status = p_status)
  ),
  counted as (select count(*) as n from scope),
  page as (
    select scope.*
    from scope
    where p_after_id is null
       or (p_after_priority is null and scope.sales_priority_score is null and scope.id > p_after_id)
       or (p_after_priority is not null and (
            scope.sales_priority_score < p_after_priority
            or (scope.sales_priority_score = p_after_priority and scope.id > p_after_id)
            or scope.sales_priority_score is null
          ))
    order by scope.sales_priority_score desc nulls last, scope.id
    limit page_size
  )
  select
    coalesce(jsonb_agg(jsonb_build_object(
      'id', page.id,
      'name', page.name,
      'city', page.city,
      'sector', page.sector,
      'status', page.status,
      'revision', page.revision,
      'sales_priority_score', page.sales_priority_score,
      'score', page.score,
      'grade', page.grade,
      'owner', (
        select jsonb_build_object('email', owner_row.user_email, 'due_at', owner_row.due_at)
        from public.lead_assignments owner_row
        where owner_row.lead_name = page.name and owner_row.status = 'active'
        limit 1
      ),
      'last_contact_at', state.latest_contact_at,
      'latest_outcome', state.latest_outcome,
      'follow_up_at', state.latest_follow_up_at
    ) order by page.sales_priority_score desc nulls last, page.id), '[]'::jsonb),
    (select n from counted)
  into rows, total
  from page
  left join public.lead_activity_state state on state.lead_id = page.id;

  last_row := rows -> (jsonb_array_length(rows) - 1);
  return jsonb_build_object(
    'items', rows,
    'total', total,
    'total_is_exact', true,
    'next_cursor', case
      when jsonb_array_length(rows) = page_size and last_row is not null
        then jsonb_build_object('priority', last_row -> 'sales_priority_score', 'id', last_row -> 'id')
      else null
    end
  );
end;
$$;
revoke all on function public.list_leads(text, boolean, integer, bigint, integer, text, text) from public, anon, authenticated;
grant execute on function public.list_leads(text, boolean, integer, bigint, integer, text, text) to service_role;

-- Readiness now also covers the scoped reads.
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
      'readable_leads', to_regprocedure('public.readable_leads(text)') is not null,
      'list_leads', to_regprocedure('public.list_leads(text,boolean,integer,bigint,integer,text,text)') is not null,
      'lead_activity_state', to_regclass('public.lead_activity_state') is not null,
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

insert into public.schema_migrations (version) values ('010') on conflict do nothing;
