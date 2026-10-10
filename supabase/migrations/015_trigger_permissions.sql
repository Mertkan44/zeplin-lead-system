-- Trigger helpers are internal; they are not application RPC endpoints.
alter function public.set_updated_at() set search_path = '';
revoke all on function public.outreach_events_refresh_state() from public, anon, authenticated, service_role;

-- Supabase's optional automatic-RLS event trigger is absent in plain Postgres.
-- Keep the trigger and its owner intact; only remove public API execution.
do $$
begin
  if to_regprocedure('public.rls_auto_enable()') is not null then
    revoke all on function public.rls_auto_enable() from public, anon, authenticated;
  end if;
end;
$$;

create index if not exists ai_token_ledger_lead_id_idx on public.ai_token_ledger(lead_id);
insert into public.schema_migrations(version) values ('015') on conflict do nothing;
