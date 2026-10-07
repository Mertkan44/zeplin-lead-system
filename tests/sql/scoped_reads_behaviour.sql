-- Behaviour checks for migration 010 (scoped reads). Rolled back.
begin;

insert into public.app_users (email, name, role, password_hash)
values ('ali@example.com', 'Ali', 'sales', 'x'), ('berk@example.com', 'Berk', 'sales', 'x');

-- 1,500 leads; priority falls with the number, every 10th has no priority.
insert into public.leads (name, city, external_id, status, sales_priority_score, raw)
select 'Lead ' || lpad(n::text, 4, '0'), 'Bursa', 'test:' || n, 'yeni',
       case when n % 10 = 0 then null else 100 - (n % 100) end, '{}'
from generate_series(1, 1500) as n;
insert into public.leads (name, city, external_id, status, raw)
values ('Yüzde%Kafe_1', 'İzmir', 'test:pct', 'yeni', '{}');

do $$
declare
  rows_found integer;
  page jsonb;
  seen bigint[] := '{}';
  cursor_priority integer;
  cursor_id bigint;
  pages integer := 0;
  late_id bigint;
  state public.lead_activity_state;
begin
  -- Access policy (same cases as the WP02 tests).
  perform public.assign_lead_owner('Lead 0001', 'ali@example.com', null, 'admin', 'active', '{}'::jsonb);
  perform public.assign_lead_owner('Lead 0001', 'berk@example.com', null, 'admin', 'active', '{}'::jsonb);
  perform public.assign_lead_owner('Lead 0002', 'ali@example.com', null, 'admin', 'active', '{}'::jsonb);
  update public.lead_assignments set status = 'done' where lead_name = 'Lead 0002';
  perform public.assign_lead_owner('Lead 0003', 'ali@example.com', null, 'admin', 'active', '{}'::jsonb);
  update public.lead_assignments set status = 'done' where lead_name = 'Lead 0003';
  perform public.assign_lead_owner('Lead 0003', 'berk@example.com', null, 'admin', 'active', '{}'::jsonb);
  perform public.assign_lead_owner('Lead 1400', 'ali@example.com', null, 'admin', 'active', '{}'::jsonb);
  perform public.assign_lead_owner('Lead 0005', 'ali@example.com', null, 'admin', 'active', '{}'::jsonb);
  update public.lead_assignments set status = 'snoozed' where lead_name = 'Lead 0005';

  assert (select array_agg(lead_name order by lead_name) from public.readable_leads('ALI@example.com'))
       = array['Lead 0002', 'Lead 0005', 'Lead 1400'],
    'Ali reads own active, closed and paused leads, not handed-over ones';
  assert (select bool_and(can_write = (lead_name = 'Lead 1400')) from public.readable_leads('ali@example.com')),
    'only the active assignment can write';
  assert (select array_agg(lead_name order by lead_name) from public.readable_leads('berk@example.com'))
       = array['Lead 0001', 'Lead 0003'],
    'Berk reads what he owns now';

  -- The 1,400th lead, far beyond any first-1000 window, is listed for its owner.
  page := public.list_leads('ali@example.com', false, null, null, 50, null, null);
  assert (page ->> 'total')::integer = 3, 'sales total covers the readable scope only';
  assert page -> 'items' @> '[{"name": "Lead 1400", "owner": {"email": "ali@example.com"}}]', 'late lead is listed with its owner';
  assert not (page -> 'items' @> '[{"name": "Lead 0001"}]'), 'handed-over lead is not listed';

  -- Admin pages through 1,501 leads: no duplicates, no gaps, unknown priority last.
  cursor_priority := null;
  cursor_id := null;
  loop
    page := public.list_leads('admin@example.com', true, cursor_priority, cursor_id, 100, null, null);
    pages := pages + 1;
    seen := seen || array(select (item ->> 'id')::bigint from jsonb_array_elements(page -> 'items') item);
    exit when page -> 'next_cursor' is null or page -> 'next_cursor' = 'null'::jsonb;
    cursor_priority := (page -> 'next_cursor' ->> 'priority')::integer;
    cursor_id := (page -> 'next_cursor' ->> 'id')::bigint;
    assert pages < 50, 'pagination terminates';
  end loop;
  assert cardinality(seen) = 1501, 'every lead listed once: ' || cardinality(seen);
  assert (select count(distinct x) from unnest(seen) x) = 1501, 'no duplicates across pages';
  assert (page ->> 'total')::integer = 1501, 'admin total is exact';
  select id into late_id from public.leads where name = 'Lead 0010';
  assert array_position(seen, late_id) > 1350, 'leads without priority come last';

  -- Search treats % and _ literally.
  page := public.list_leads('admin@example.com', true, null, null, 50, 'e%K', null);
  assert (page ->> 'total')::integer = 1, 'percent sign is literal';
  page := public.list_leads('admin@example.com', true, null, null, 50, 'Lead 14', null);
  assert (page ->> 'total')::integer = 100, 'search by name matches Lead 1400-1499: ' || (page ->> 'total');

  -- Projection: an old verification survives 10,000 newer events.
  insert into public.outreach_events (lead_name, action, note, happened_at)
  values ('Lead 1400', 'manual_verification_saved', 'ZEPLIN_MANUAL_V1:{"kind":"manual_verification"}', now() - interval '90 days');
  insert into public.outreach_events (lead_name, action, note, happened_at, outcome, follow_up_at, actor_email)
  values ('Lead 1400', 'contact_result_recorded', 'x', now() - interval '80 days', 'no_answer', now() - interval '79 days', 'ALI@example.com');
  insert into public.outreach_events (lead_name, action, note, happened_at)
  select 'Lead ' || lpad((1 + n % 1300)::text, 4, '0'), 'note_added', 'busy', now() - (n || ' seconds')::interval
  from generate_series(1, 10000) as n;
  select * into state from public.lead_activity_state where lead_id = (select id from public.leads where name = 'Lead 1400');
  assert state.latest_manual_verification is not null, 'old verification kept';
  assert state.latest_outcome = 'no_answer' and state.contact_result_count = 1, 'latest contact kept';
  assert state.latest_contact_actor = 'ali@example.com', 'actor normalised';

  -- A legacy note-encoded result is decoded; a malformed one does not break the write.
  insert into public.outreach_events (lead_name, action, note, happened_at)
  values ('Lead 1400', 'contact_result_recorded',
          'ZEPLIN_ACTIVITY_V1:{"outcome":"reached_later","follow_up_at":"2026-12-01T07:00:00+00:00"}', now());
  select * into state from public.lead_activity_state where lead_id = (select id from public.leads where name = 'Lead 1400');
  assert state.latest_outcome = 'reached_later' and state.latest_follow_up_at = '2026-12-01T07:00:00+00:00',
    'legacy note decoded';
  insert into public.outreach_events (lead_name, action, note, happened_at)
  values ('Lead 1400', 'contact_result_recorded', 'ZEPLIN_ACTIVITY_V1:{not json', now() + interval '1 second');
  select * into state from public.lead_activity_state where lead_id = (select id from public.leads where name = 'Lead 1400');
  assert state.contact_result_count = 3 and state.latest_outcome is null, 'malformed note tolerated';

  -- Moving events to another lead refreshes both sides; rebuild is idempotent.
  update public.outreach_events set lead_name = 'Lead 0002', lead_id = null
  where lead_name = 'Lead 1400' and action = 'manual_verification_saved';
  assert (select latest_manual_verification is null from public.lead_activity_state
          where lead_id = (select id from public.leads where name = 'Lead 1400')), 'old lead cleared';
  assert (select latest_manual_verification is not null from public.lead_activity_state
          where lead_id = (select id from public.leads where name = 'Lead 0002')), 'new lead updated';
  perform public.rebuild_lead_activity_state();
  assert (select contact_result_count from public.lead_activity_state
          where lead_id = (select id from public.leads where name = 'Lead 1400')) = 3, 'rebuild keeps counts';

  -- list_leads shows the projection.
  page := public.list_leads('ali@example.com', false, null, null, 50, '1400', null);
  assert page -> 'items' -> 0 ->> 'latest_outcome' is null and page -> 'items' -> 0 ->> 'last_contact_at' is not null,
    'list carries the latest contact';
end $$;

rollback;
