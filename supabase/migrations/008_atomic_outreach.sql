-- Apply after 006 and 007. A single transaction records an outreach action and
-- advances the lead/assignment only if the event was newly inserted.
drop index if exists public.outreach_events_idempotency_uidx;
create unique index if not exists outreach_events_idempotency_uidx
  on public.outreach_events (idempotency_key);

create or replace function public.record_outreach_action(
  target_lead_name text,
  target_action text,
  target_note text,
  target_happened_at timestamptz,
  target_actor_email text,
  target_source text,
  target_idempotency_key text,
  target_status text default null,
  target_assignment_status text default null,
  target_follow_up_at timestamptz default null,
  target_assignment_meta jsonb default '{}'::jsonb,
  target_activity jsonb default '{}'::jsonb
)
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
  saved public.outreach_events;
  existing public.outreach_events;
  newer_event_at timestamptz;
  current_status text;
begin
  if nullif(target_idempotency_key, '') is null then
    raise exception 'idempotency key is required';
  end if;
  if target_status is not null and target_status not in
    ('yeni', 'ready', 'missing_info', 'contacted', 'follow_up', 'converted', 'lost') then
    raise exception 'invalid lead status';
  end if;
  if target_assignment_status is not null and target_assignment_status not in
    ('active', 'done', 'snoozed', 'archived') then
    raise exception 'invalid assignment status';
  end if;
  select status into current_status from public.leads
    where name = target_lead_name for update;
  if not found then
    raise exception 'lead not found';
  end if;

  select max(happened_at) into newer_event_at from public.outreach_events
    where lead_name = target_lead_name
      and action in ('contact_result_recorded', 'deal_won', 'deal_lost');

  insert into public.outreach_events (
    lead_name, action, note, happened_at, actor_email, source, idempotency_key,
    channel, outcome, follow_up_at, service_slugs, contact_name
  ) values (
    target_lead_name, target_action, target_note,
    coalesce(target_happened_at, now()), lower(target_actor_email),
    target_source, target_idempotency_key,
    target_activity->>'channel', target_activity->>'outcome',
    (target_activity->>'follow_up_at')::timestamptz,
    coalesce(array(select jsonb_array_elements_text(target_activity->'service_slugs')), '{}'),
    target_activity->>'contact_name'
  )
  on conflict (idempotency_key) do nothing
  returning * into saved;

  if saved.id is null then
    select * into existing from public.outreach_events
    where idempotency_key = target_idempotency_key;
    if existing.lead_name is distinct from target_lead_name
       or existing.actor_email is distinct from lower(target_actor_email)
       or existing.action is distinct from target_action then
      raise exception 'idempotency key reused for a different action';
    end if;
    return jsonb_build_object('inserted', false, 'event', to_jsonb(existing));
  end if;

  if current_status in ('converted', 'lost')
     and target_status is not null and target_status <> current_status then
    raise exception 'closed lead must be reopened before a new contact result';
  end if;

  if target_action in ('contact_result_recorded', 'deal_won', 'deal_lost')
     and newer_event_at is not null and saved.happened_at < newer_event_at then
    return jsonb_build_object('inserted', true, 'stale', true, 'event', to_jsonb(saved));
  end if;

  if target_status is not null then
    update public.leads
      set status = target_status, updated_at = now()
    where name = target_lead_name;
  end if;
  if target_assignment_status is not null then
    update public.lead_assignments
      set status = target_assignment_status,
          due_at = target_follow_up_at,
          meta = coalesce(meta, '{}'::jsonb) || coalesce(target_assignment_meta, '{}'::jsonb),
          updated_at = now()
    where lead_name = target_lead_name and status = 'active';
  end if;
  return jsonb_build_object('inserted', true, 'event', to_jsonb(saved));
end;
$$;

revoke all on function public.record_outreach_action(
  text, text, text, timestamptz, text, text, text, text, text, timestamptz, jsonb, jsonb
) from public, anon, authenticated;
grant execute on function public.record_outreach_action(
  text, text, text, timestamptz, text, text, text, text, text, timestamptz, jsonb, jsonb
) to service_role;
