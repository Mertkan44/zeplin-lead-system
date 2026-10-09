-- Behaviour checks for the AI generation lease and spend summary (migration 011). Rolled back.
begin;

insert into public.leads (name, city, external_id, status, raw)
values ('Demo Cafe', 'Bursa', 'test:cafe', 'yeni', '{}');

create function pg_temp.claim(key text, owner text, lease integer default 180) returns jsonb language sql as $$
  select public.claim_ai_generation(
    key, 'report', owner, lease, 'deepseek', 'deepseek-v4-flash',
    (select id from public.leads where name = 'Demo Cafe'), 'input-1', '7', 'catalog-1'
  );
$$;

do $$
declare
  result jsonb;
  rows_found integer;
  summary jsonb;
begin
  -- First caller gets the lease; a second one is told to wait.
  result := pg_temp.claim('key-1', 'worker-a');
  assert result ->> 'status' = 'claimed', 'first caller claims';
  result := pg_temp.claim('key-1', 'worker-b');
  assert result ->> 'status' = 'busy', 'second caller sees busy while the lease is live';

  -- Completion makes the text available to everyone; a late second completion changes nothing.
  assert public.complete_ai_generation('key-1', 'rapor', 'deepseek', 'deepseek-v4-flash', '{"total_tokens": 10}'::jsonb),
    'first completion stored';
  assert not public.complete_ai_generation('key-1', 'başka', 'deepseek', 'deepseek-v4-pro', '{}'::jsonb),
    'second completion ignored';
  result := pg_temp.claim('key-1', 'worker-b');
  assert result ->> 'status' = 'ready' and result ->> 'content' = 'rapor', 'later caller reads the finished text';
  select count(*) into rows_found from public.ai_generations
  where cache_key = 'key-1' and input_hash = 'input-1' and catalog_version = 'catalog-1'
    and requested_model = 'deepseek-v4-flash' and lead_id is not null;
  assert rows_found = 1, 'generation records its input';

  -- A failed generation is taken over by the next caller.
  result := pg_temp.claim('key-2', 'worker-a');
  perform public.fail_ai_generation('key-2', 'worker-a', 'HTTPError: boom');
  assert (select status from public.ai_generations where cache_key = 'key-2') = 'failed', 'failure recorded';
  result := pg_temp.claim('key-2', 'worker-b');
  assert result ->> 'status' = 'claimed', 'failed key is claimed again';
  assert (select attempts from public.ai_generations where cache_key = 'key-2') = 2, 'attempts counted';

  -- An expired lease is taken over too; another owner cannot fail it.
  result := pg_temp.claim('key-3', 'worker-a', 10);
  update public.ai_generations set claimed_until = now() - interval '1 second' where cache_key = 'key-3';
  result := pg_temp.claim('key-3', 'worker-b');
  assert result ->> 'status' = 'claimed', 'expired lease is taken over';
  perform public.fail_ai_generation('key-3', 'worker-a', 'late failure');
  assert (select status from public.ai_generations where cache_key = 'key-3') = 'pending', 'old owner cannot fail a taken-over lease';

  -- Rows written before 011 (status defaults to ready) are served as before.
  insert into public.ai_generations (cache_key, task, provider, model, content) values ('legacy', 'report', 'deepseek', 'm', 'eski');
  assert pg_temp.claim('legacy', 'worker-a') ->> 'status' = 'ready', 'legacy row is a hit';

  -- Ledger: one reservation released, one open; usage, a cache hit, a failure, an unpriced call.
  insert into public.admin_search_jobs (id, query, city, max_results, deep_research, ai_mode, created_by, status)
  overriding system value values (9001, 'q', 'c', 1, true, 'smart', 'a', 'success'), (9002, 'q', 'c', 1, true, 'smart', 'a', 'queued');
  insert into public.ai_token_ledger (job_id, kind, estimated_tokens, estimated_cost_usd) values
    (9001, 'reservation', 9000, 0.01), (9002, 'reservation', 18000, 0.02);
  insert into public.ai_token_ledger (job_id, kind) values (9001, 'release');
  insert into public.ai_token_ledger (kind, task, model, outcome, actual_tokens, actual_cost_usd, created_at) values
    ('usage', 'report', 'deepseek-v4-flash', 'success', 1000, 0.0005, now()),
    ('usage', 'report', 'deepseek-v4-flash', 'cache_hit', 0, 0, now()),
    ('usage', 'email', 'deepseek-v4-pro', 'error', 0, null, now()),
    ('usage', 'email', 'other-model', 'success', 500, null, now() - interval '3 days');
  summary := public.ai_spend_summary(now() - interval '1 day');
  assert (summary ->> 'actual_cost_usd')::numeric = 0.0005, 'actual cost summed';
  assert (summary ->> 'actual_tokens')::integer = 1500, 'actual tokens summed';
  assert (summary ->> 'provider_calls')::integer = 3, 'cache hits are not provider calls';
  assert (summary ->> 'cache_hits')::integer = 1, 'cache hit counted';
  assert (summary ->> 'failed_calls')::integer = 1, 'failed call counted';
  assert (summary ->> 'unpriced_calls')::integer = 1, 'call without a price counted';
  assert (summary ->> 'active_reserved_usd')::numeric = 0.02, 'released reservation no longer active';
  assert (summary ->> 'estimated_cost_usd')::numeric = 0.03, 'historical estimates kept';
  assert (summary ->> 'today_cost_usd')::numeric = 0.0005, 'today window applied';
  assert (summary -> 'by_task' -> 'report' ->> 'calls')::integer = 1, 'per-task totals exclude cache hits';
end;
$$;

rollback;
