-- Exercise both the plain-Postgres and optional Supabase event-trigger paths.
begin;
create function public.rls_auto_enable() returns event_trigger
language plpgsql security definer set search_path=pg_catalog as $$ begin end $$;
grant execute on function public.rls_auto_enable() to public, anon, authenticated;
\ir ../../supabase/migrations/015_trigger_permissions.sql

do $$
begin
  assert not has_function_privilege('anon','public.rls_auto_enable()','EXECUTE');
  assert not has_function_privilege('authenticated','public.rls_auto_enable()','EXECUTE');
  assert not has_function_privilege('anon','public.outreach_events_refresh_state()','EXECUTE');
  assert not has_function_privilege('authenticated','public.outreach_events_refresh_state()','EXECUTE');
  assert not has_function_privilege('service_role','public.outreach_events_refresh_state()','EXECUTE');
end $$;

insert into public.leads(name,city,external_id,raw,updated_at)
values ('Trigger permission probe','Istanbul','security:trigger-probe','{}','2000-01-01');
set local role service_role;
-- Use the actual application command, including its SECURITY DEFINER boundary.
select public.record_contact_result('security-trigger-probe-01','synthetic-hash',
  'admin@example.com',true,'Trigger permission probe',0,'phone','reached_later',
  now()+interval '1 day',array[]::text[],null,'Synthetic permission probe','follow_up','active');
reset role;
do $$
begin
  assert (select updated_at > '2000-01-01' from public.leads where external_id='security:trigger-probe'),
    'timestamp trigger still runs under service role';
  assert exists(select 1 from public.lead_activity_state s join public.leads l on s.lead_id=l.id
    where l.external_id='security:trigger-probe'), 'activity trigger still runs without direct RPC permission';
end $$;
rollback;
