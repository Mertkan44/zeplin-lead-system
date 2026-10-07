-- Behaviour checks for record_contact_result (migration 009). Rolled back.
begin;

insert into public.app_users (email, name, role, password_hash)
values ('ali@example.com', 'Ali', 'sales', 'x'), ('berk@example.com', 'Berk', 'sales', 'x');
insert into public.leads (name, city, external_id, status, raw)
values ('Demo Cafe', 'Bursa', 'test:cafe', 'yeni', '{}'), ('Demo Bar', 'Bursa', 'test:bar', 'yeni', '{}');
select public.assign_lead_owner('Demo Cafe', 'ali@example.com', null, 'admin@example.com', 'active', '{}'::jsonb);
select public.assign_lead_owner('Demo Bar', 'ali@example.com', null, 'admin@example.com', 'active', '{}'::jsonb);

-- Helper so each call below stays short.
create function pg_temp.record(
  key text, hash text, actor text, is_admin boolean, lead text, expected integer,
  outcome text, follow_up timestamptz, lead_status text, assignment_status text
) returns jsonb language sql as $$
  select public.record_contact_result(
    key, hash, actor, is_admin, lead, expected, 'phone', outcome, follow_up,
    array['web-tasarim'], 'Ayşe', 'note', lead_status, assignment_status
  );
$$;

do $$
declare
  first jsonb;
  again jsonb;
  rows_found integer;
  failed boolean;
  rev integer;
begin
  -- Owner records a result: event, status, revision and follow-up together.
  first := pg_temp.record('11111111-1111-4111-8111-111111111111', 'h1', 'ali@example.com', false,
                          'Demo Cafe', 0, 'no_answer', '2026-10-08T07:00:00Z', 'follow_up', 'active');
  assert (first ->> 'replayed')::boolean = false, 'first call is not a replay';
  assert (first ->> 'lead_revision')::integer = 1, 'revision bumped';
  select count(*) into rows_found from public.outreach_events
  where lead_name = 'Demo Cafe' and outcome = 'no_answer' and channel = 'phone' and lead_id is not null;
  assert rows_found = 1, 'event stored with native columns';
  select count(*) into rows_found from public.leads where name = 'Demo Cafe' and status = 'follow_up';
  assert rows_found = 1, 'lead status updated';
  select count(*) into rows_found from public.lead_assignments
  where lead_name = 'Demo Cafe' and status = 'active' and due_at = '2026-10-08T07:00:00Z';
  assert rows_found = 1, 'owner follow-up date set';

  -- The same submission again: same answer, nothing written twice.
  again := pg_temp.record('11111111-1111-4111-8111-111111111111', 'h1', 'ali@example.com', false,
                          'Demo Cafe', 0, 'no_answer', '2026-10-08T07:00:00Z', 'follow_up', 'active');
  assert (again ->> 'replayed')::boolean, 'retry is a replay';
  assert again ->> 'event_id' = first ->> 'event_id', 'retry returns the original event';
  select count(*) into rows_found from public.outreach_events where lead_name = 'Demo Cafe';
  assert rows_found = 1, 'retry writes no second event';

  -- Same key, different payload: rejected.
  begin
    perform pg_temp.record('11111111-1111-4111-8111-111111111111', 'h2', 'ali@example.com', false,
                           'Demo Cafe', 1, 'won', null, 'converted', 'done');
    failed := false;
  exception when sqlstate 'PT409' then failed := true;
  end;
  assert failed, 'reused key with another payload is rejected';

  -- A newer result, then an old retry of the first one cannot roll it back.
  perform pg_temp.record('22222222-2222-4222-8222-222222222222', 'h3', 'ali@example.com', false,
                         'Demo Cafe', 1, 'won', null, 'converted', 'done');
  perform pg_temp.record('11111111-1111-4111-8111-111111111111', 'h1', 'ali@example.com', false,
                         'Demo Cafe', 0, 'no_answer', '2026-10-08T07:00:00Z', 'follow_up', 'active');
  select revision into rev from public.leads where name = 'Demo Cafe';
  select count(*) into rows_found from public.leads where name = 'Demo Cafe' and status = 'converted';
  assert rows_found = 1 and rev = 2, 'stale retry does not move the stage back';
  -- Won closes the follow-up.
  select count(*) into rows_found from public.lead_assignments
  where lead_name = 'Demo Cafe' and status = 'done' and due_at is null;
  assert rows_found = 1, 'won closes the open follow-up';

  -- Someone who does not own the lead is refused; admins are allowed.
  begin
    perform pg_temp.record('33333333-3333-4333-8333-333333333333', 'h4', 'berk@example.com', false,
                           'Demo Bar', null, 'no_answer', null, 'follow_up', 'active');
    failed := false;
  exception when sqlstate 'PT403' then failed := true;
  end;
  assert failed, 'non-owner is refused';
  perform pg_temp.record('44444444-4444-4444-8444-444444444444', 'h5', 'admin@example.com', true,
                         'Demo Bar', null, 'reached_later', '2026-10-09T07:00:00Z', 'follow_up', 'active');

  -- A stale revision is refused and leaves no trace.
  begin
    perform pg_temp.record('55555555-5555-4555-8555-555555555555', 'h6', 'ali@example.com', false,
                           'Demo Bar', 0, 'reached_interested', null, 'contacted', 'active');
    failed := false;
  exception when sqlstate 'PT409' then failed := true;
  end;
  assert failed, 'stale revision is refused';
  select count(*) into rows_found from public.command_requests
  where idempotency_key = '55555555-5555-4555-8555-555555555555';
  assert rows_found = 0, 'refused command stores nothing';

  -- A failure after the event insert rolls everything back (invalid status).
  begin
    perform pg_temp.record('66666666-6666-4666-8666-666666666666', 'h7', 'ali@example.com', false,
                           'Demo Bar', null, 'reached_interested', null, 'not-a-status', 'active');
    failed := false;
  exception when check_violation then failed := true;
  end;
  assert failed, 'invalid status fails';
  select count(*) into rows_found from public.outreach_events
  where idempotency_key = '66666666-6666-4666-8666-666666666666';
  assert rows_found = 0, 'event of the failed command is rolled back';

  -- Wrong number flags the phone for verification.
  perform pg_temp.record('77777777-7777-4777-8777-777777777777', 'h8', 'ali@example.com', false,
                         'Demo Bar', null, 'wrong_number', null, 'missing_info', 'active');
  select count(*) into rows_found from public.lead_assignments
  where lead_name = 'Demo Bar' and meta ->> 'needs_verification' = 'phone' and due_at is null;
  assert rows_found = 1, 'wrong number asks for phone verification';

  -- Status changes outside the command also bump the revision.
  select revision into rev from public.leads where name = 'Demo Bar';
  update public.leads set status = 'lost' where name = 'Demo Bar';
  assert (select revision from public.leads where name = 'Demo Bar') = rev + 1, 'status change bumps revision';
  update public.leads set raw = raw where name = 'Demo Bar';
  assert (select revision from public.leads where name = 'Demo Bar') = rev + 1, 'non-CRM update keeps revision';
end $$;

rollback;
