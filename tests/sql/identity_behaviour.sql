-- Behaviour checks for the schema, run by scripts/schema_parity.py against a
-- fresh database. Everything happens in one transaction that is rolled back.
begin;

insert into public.app_users (email, name, role, password_hash)
values ('ali@example.com', 'Ali', 'sales', 'x'), ('berk@example.com', 'Berk', 'sales', 'x');

do $$
declare
  cafe_id bigint;
  twin_id bigint;
  event_lead_id bigint;
  rows_found integer;
  readiness jsonb;
begin
  -- A lead with a Google place id in its Maps URL records that identity.
  insert into public.leads (name, city, external_id, maps_url, raw)
  values ('Demo Cafe', 'Bursa', 'test:cafe',
          'https://www.google.com/maps/place/Demo/data=!4m7!3m6!19sChIJdemoPlace0001?hl=tr', '{}')
  returning id into cafe_id;
  select count(*) into rows_found from public.lead_sources
  where provider = 'google_places' and provider_id = 'ChIJdemoPlace0001' and lead_id = cafe_id;
  assert rows_found = 1, 'place id from maps_url is recorded';

  -- A verified Places API id wins over the URL id.
  update public.leads
  set raw = '{"research": {"google_places": {"status": "verified", "place_id": "ChIJverified00001"}}}'
  where id = cafe_id;
  select count(*) into rows_found from public.lead_sources
  where provider_id = 'ChIJverified00001' and lead_id = cafe_id;
  assert rows_found = 1, 'verified Places id is recorded';

  -- Re-saving the same lead does not duplicate its source row.
  update public.leads set raw = raw where id = cafe_id;
  select count(*) into rows_found from public.lead_sources where lead_id = cafe_id;
  assert rows_found = 2, 'one row per provider id';

  -- Same place under another name is NOT merged into the first lead.
  insert into public.leads (name, city, external_id, maps_url, raw)
  values ('Demo Cafe Nilüfer', 'Bursa', 'test:twin',
          'https://www.google.com/maps/place/Twin/data=!4m7!19sChIJdemoPlace0001', '{}')
  returning id into twin_id;
  select lead_id into event_lead_id from public.lead_sources where provider_id = 'ChIJdemoPlace0001';
  assert event_lead_id = cafe_id, 'shared place id stays with the first lead';
  select count(*) into rows_found from public.leads where id in (cafe_id, twin_id);
  assert rows_found = 2, 'both leads still exist';

  -- Events and assignments get lead_id from lead_name.
  insert into public.outreach_events (lead_name, action, idempotency_key)
  values ('Demo Cafe', 'note_added', 'key-1');
  select lead_id into event_lead_id from public.outreach_events where idempotency_key = 'key-1';
  assert event_lead_id = cafe_id, 'outreach event lead_id is filled';
  perform public.assign_lead_owner('Demo Cafe', 'ali@example.com', null, 'admin@example.com', 'active', '{}'::jsonb);
  select lead_id into event_lead_id from public.lead_assignments where lead_name = 'Demo Cafe';
  assert event_lead_id = cafe_id, 'assignment lead_id is filled';

  -- What PostgREST sends for on_conflict=idempotency_key: the retry is ignored.
  insert into public.outreach_events (lead_name, action, idempotency_key)
  values ('Demo Cafe', 'note_added', 'key-1')
  on conflict (idempotency_key) do nothing;
  select count(*) into rows_found from public.outreach_events where idempotency_key = 'key-1';
  assert rows_found = 1, 'idempotent retry inserts nothing';
  insert into public.outreach_events (lead_name, action) values ('Demo Cafe', 'note_added');
  insert into public.outreach_events (lead_name, action) values ('Demo Cafe', 'note_added');

  -- Renaming a lead keeps its history attached.
  update public.leads set name = 'Demo Cafe Bursa' where id = cafe_id;
  select count(*) into rows_found from public.outreach_events
  where lead_name = 'Demo Cafe Bursa' and lead_id = cafe_id;
  assert rows_found = 3, 'events follow the renamed lead';
  select count(*) into rows_found from public.lead_assignments
  where lead_name = 'Demo Cafe Bursa' and lead_id = cafe_id and status = 'active';
  assert rows_found = 1, 'assignment follows the renamed lead';

  -- Readiness reports every check as passing.
  readiness := public.schema_readiness();
  assert readiness ->> 'version' >= '008', 'schema version is recorded';
  assert not exists (
    select 1 from jsonb_each(readiness -> 'checks') where value <> 'true'::jsonb
  ), 'all readiness checks pass: ' || (readiness -> 'checks')::text;

  -- Deleting a lead removes its dependent rows.
  delete from public.leads where id = cafe_id;
  select count(*) into rows_found from public.lead_sources where lead_id = cafe_id;
  assert rows_found = 0, 'sources cascade on delete';
  select count(*) into rows_found from public.outreach_events where lead_id = cafe_id;
  assert rows_found = 0, 'events cascade on delete';
end $$;

rollback;
