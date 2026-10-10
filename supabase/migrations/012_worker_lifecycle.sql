-- Durable, fenced worker ownership. Apply before rolling out the new worker;
-- pause/drain old Actions runs first (the legacy claim RPC is retired below).
alter table public.admin_search_jobs drop constraint if exists admin_search_jobs_status_check;
alter table public.admin_search_jobs add constraint admin_search_jobs_status_check
  check (status in ('queued','running','retry_wait','success','partial_success','failed','cancelled'));
alter table public.admin_search_jobs add column if not exists lease_owner text;
alter table public.admin_search_jobs add column if not exists lease_until timestamptz;
alter table public.admin_search_jobs add column if not exists heartbeat_at timestamptz;
alter table public.admin_search_jobs add column if not exists attempt_count integer not null default 0;
alter table public.admin_search_jobs add column if not exists max_attempts integer not null default 3;
alter table public.admin_search_jobs add column if not exists next_attempt_at timestamptz;
alter table public.admin_search_jobs add column if not exists progress_stage text not null default 'queued';
alter table public.admin_search_jobs add column if not exists progress_done integer not null default 0;
alter table public.admin_search_jobs add column if not exists progress_total integer not null default 0;
alter table public.admin_search_jobs add column if not exists last_error jsonb;
-- Legacy jobs get a grace period; do not steal an old worker's live work.
update public.admin_search_jobs set lease_owner='legacy', lease_until=now()+interval '1 hour', attempt_count=1
where status='running' and lease_owner is null;

create table if not exists public.admin_search_checkpoints (
  job_id bigint not null references public.admin_search_jobs(id) on delete cascade,
  item_key text not null,
  stage text not null,
  payload jsonb not null default '{}'::jsonb,
  lead_id bigint references public.leads(id) on delete set null,
  error jsonb,
  updated_at timestamptz not null default now(),
  primary key (job_id,item_key)
);
alter table public.admin_search_checkpoints enable row level security;
grant select,insert,update,delete on public.admin_search_checkpoints to service_role;
create index if not exists admin_search_checkpoints_lead_idx on public.admin_search_checkpoints(lead_id,job_id);

-- Close reservations atomically with terminal transitions (including recovery).
create or replace function public.close_search_reservation(p_job_id bigint, p_status text)
returns void language plpgsql security definer set search_path=public as $$
begin
  perform 1 from public.admin_search_jobs where id=p_job_id for update;
  insert into public.ai_token_ledger(job_id,kind,meta)
  select p_job_id,'release',jsonb_build_object('job_status',p_status)
  where not exists (select 1 from public.ai_token_ledger where job_id=p_job_id and kind='release');
end;
$$;

create or replace function public.claim_search_job(p_owner text)
returns setof public.admin_search_jobs language plpgsql security definer set search_path=public as $$
declare exhausted public.admin_search_jobs;
begin
  if coalesce(p_owner,'')='' then raise exception 'owner required'; end if;
  for exhausted in
    update public.admin_search_jobs set status=case when exists(select 1 from public.admin_search_checkpoints c where c.job_id=admin_search_jobs.id and c.lead_id is not null) then 'partial_success' else 'failed' end,
      lease_owner=null,lease_until=null,updated_at=now(),
      last_error=jsonb_build_object('stage',progress_stage,'code','retry_limit','message','Tarama deneme sınırına ulaştı.')
    where status='running' and lease_until<=now() and attempt_count>=max_attempts returning *
  loop perform public.close_search_reservation(exhausted.id,exhausted.status); end loop;
  return query
  with candidate as (
    select id from public.admin_search_jobs
    where attempt_count<max_attempts and (
      status='queued' or (status='retry_wait' and next_attempt_at<=now())
      or (status='running' and lease_until<=now()))
    order by created_at,id for update skip locked limit 1
  )
  update public.admin_search_jobs j set status='running',lease_owner=p_owner,
    lease_until=now()+interval '3 minutes',heartbeat_at=now(),updated_at=now(),
    attempt_count=attempt_count+1,next_attempt_at=null,progress_stage='starting'
  from candidate where j.id=candidate.id returning j.*;
end;
$$;

create or replace function public.heartbeat_search_job(p_job_id bigint,p_owner text)
returns boolean language plpgsql security definer set search_path=public as $$
begin
  update public.admin_search_jobs set heartbeat_at=now(),lease_until=now()+interval '3 minutes',updated_at=now()
  where id=p_job_id and status='running' and lease_owner=p_owner and lease_until>now();
  return found;
end;
$$;

create or replace function public.checkpoint_search_job(
  p_job_id bigint,p_owner text,p_item_key text,p_stage text,p_payload jsonb,p_lead_id bigint,p_error jsonb
)
returns boolean language plpgsql security definer set search_path=public as $$
begin
  perform 1 from public.admin_search_jobs where id=p_job_id and status='running'
    and lease_owner=p_owner and lease_until>now() for update;
  if not found then return false; end if;
  insert into public.admin_search_checkpoints(job_id,item_key,stage,payload,lead_id,error)
  values(p_job_id,p_item_key,p_stage,p_payload,p_lead_id,p_error)
  on conflict(job_id,item_key) do update set stage=excluded.stage,payload=excluded.payload,
    lead_id=coalesce(excluded.lead_id,admin_search_checkpoints.lead_id),error=excluded.error,updated_at=now();
  update public.admin_search_jobs set progress_stage=p_stage,updated_at=now(),
    progress_done=(select count(*) from public.admin_search_checkpoints where job_id=p_job_id and stage='synced'),
    progress_total=case when p_item_key='_discovery' then jsonb_array_length(p_payload->'items') else progress_total end,
    last_error=p_error
  where id=p_job_id;
  return true;
end;
$$;

create or replace function public.finish_search_job(p_job_id bigint,p_owner text,p_result jsonb,p_error jsonb)
returns text language plpgsql security definer set search_path=public as $$
declare job public.admin_search_jobs; final_status text;
begin
  select * into job from public.admin_search_jobs where id=p_job_id and status='running'
    and lease_owner=p_owner and lease_until>now() for update;
  if not found then return 'lease_lost'; end if;
  final_status := case when p_error is null then 'success'
    when job.attempt_count<job.max_attempts then 'retry_wait'
    when exists(select 1 from public.admin_search_checkpoints where job_id=p_job_id and lead_id is not null)
      then 'partial_success' else 'failed' end;
  update public.admin_search_jobs set status=final_status,result=p_result,last_error=p_error,
    lease_owner=null,lease_until=null,updated_at=now(),
    next_attempt_at=case when final_status='retry_wait' then now()+make_interval(secs=>60*job.attempt_count) end,
    progress_stage=case when final_status='success' then 'complete' else progress_stage end
  where id=p_job_id;
  if final_status<>'retry_wait' then perform public.close_search_reservation(p_job_id,final_status); end if;
  return final_status;
end;
$$;

create or replace function public.control_search_job(p_job_id bigint,p_action text)
returns jsonb language plpgsql security definer set search_path=public as $$
declare job public.admin_search_jobs;
begin
  select * into job from public.admin_search_jobs where id=p_job_id for update;
  if not found then return jsonb_build_object('ok',false,'code','not_found'); end if;
  if p_action='cancel' then
    if job.status='cancelled' then return jsonb_build_object('ok',true); end if;
    if job.status not in ('queued','running','retry_wait') then return jsonb_build_object('ok',false,'code','terminal'); end if;
    update public.admin_search_jobs set status='cancelled',lease_owner=null,lease_until=null,updated_at=now() where id=p_job_id;
    perform public.close_search_reservation(p_job_id,'cancelled');
  elsif p_action='retry' then
    if job.status in ('queued','retry_wait') then return jsonb_build_object('ok',true); end if;
    if job.status not in ('failed','partial_success') or job.attempt_count>=job.max_attempts
      then return jsonb_build_object('ok',false,'code','retry_limit'); end if;
    update public.admin_search_jobs set status='retry_wait',next_attempt_at=now(),updated_at=now() where id=p_job_id;
  else return jsonb_build_object('ok',false,'code','invalid_action'); end if;
  return jsonb_build_object('ok',true);
end;
$$;

-- Retire the unfenced claim path. Older API reads and writes remain compatible;
-- an old worker must fail closed rather than bypass bounded retries.
create or replace function public.claim_admin_search_jobs(job_limit integer default 1)
returns setof public.admin_search_jobs language plpgsql security definer set search_path=public as $$
begin raise exception 'Worker migration 012 requires scripts/process_search_jobs.py from WP12'; end;
$$;

-- Completion is fenced by the actual generation owner. The old completion RPC
-- remains for compatibility with an earlier API deployment.
create or replace function public.complete_owned_ai_generation(
 p_cache_key text,p_owner text,p_content text,p_provider text,p_model text,p_usage jsonb
)
returns boolean language plpgsql security definer set search_path=public as $$
begin
 update public.ai_generations set status='ready',content=p_content,provider=p_provider,model=p_model,
   usage=coalesce(p_usage,'{}'::jsonb),claimed_by=null,claimed_until=null,error=null
 where cache_key=p_cache_key and status='pending' and claimed_by=p_owner and claimed_until>now();
 return found;
end;
$$;

revoke all on function public.close_search_reservation(bigint,text) from public;
revoke all on function public.claim_search_job(text) from public;
revoke all on function public.heartbeat_search_job(bigint,text) from public;
revoke all on function public.checkpoint_search_job(bigint,text,text,text,jsonb,bigint,jsonb) from public;
revoke all on function public.finish_search_job(bigint,text,jsonb,jsonb) from public;
revoke all on function public.control_search_job(bigint,text) from public;
revoke all on function public.complete_owned_ai_generation(text,text,text,text,text,jsonb) from public;
grant execute on function public.close_search_reservation(bigint,text) to service_role;
grant execute on function public.claim_search_job(text) to service_role;
grant execute on function public.heartbeat_search_job(bigint,text) to service_role;
grant execute on function public.checkpoint_search_job(bigint,text,text,text,jsonb,bigint,jsonb) to service_role;
grant execute on function public.finish_search_job(bigint,text,jsonb,jsonb) to service_role;
grant execute on function public.control_search_job(bigint,text) to service_role;
grant execute on function public.complete_owned_ai_generation(text,text,text,text,text,jsonb) to service_role;

-- Worker calls have a generation retry cap in addition to the job cap. A cached
-- success is always readable. Lock the job first, then the generation everywhere.
create or replace function public.claim_worker_ai_generation(
 p_job_id bigint,p_job_owner text,p_cache_key text,p_task text,p_owner text,p_lease_seconds integer,
 p_provider text,p_requested_model text,p_lead_id bigint,p_input_hash text,p_prompt_version text,p_catalog_version text
)
returns jsonb language plpgsql security definer set search_path=public as $$
declare generation public.ai_generations;
begin
 perform 1 from public.admin_search_jobs where id=p_job_id and status='running'
   and lease_owner=p_job_owner and lease_until>now() for update;
 if not found then return jsonb_build_object('status','lease_lost'); end if;
 select * into generation from public.ai_generations where cache_key=p_cache_key for update;
 if found and generation.status<>'ready' and generation.attempts>=3 then
   return jsonb_build_object('status','exhausted');
 end if;
 return public.claim_ai_generation(p_cache_key,p_task,p_owner,p_lease_seconds,p_provider,p_requested_model,
   p_lead_id,p_input_hash,p_prompt_version,p_catalog_version);
end;
$$;
revoke all on function public.claim_worker_ai_generation(bigint,text,text,text,text,integer,text,text,bigint,text,text,text) from public;
grant execute on function public.claim_worker_ai_generation(bigint,text,text,text,text,integer,text,text,bigint,text,text,text) to service_role;

-- Workers refresh scrape/research data, never the trusted Places record. Keep
-- that source current even if a Places refresh raced with the frozen AI input.
create or replace function public.merge_worker_raw(p_previous jsonb,p_incoming jsonb,p_audit boolean)
returns jsonb language plpgsql immutable set search_path=public as $$
declare merged jsonb;
begin
 if p_audit then
   p_incoming:=p_incoming - array['research_brief','ai_report','ai_email','ai_input_hash','ai_prompt_version','ai_generated_at'];
 end if;
 merged:=p_previous||p_incoming;
 if p_previous#>'{research,google_places}' is not null then
   merged:=jsonb_set(merged,'{research}',coalesce(p_previous->'research','{}'::jsonb)||
     coalesce(p_incoming->'research','{}'::jsonb)||jsonb_build_object('google_places',p_previous#>'{research,google_places}'));
 end if;
 return merged;
end;
$$;
revoke all on function public.merge_worker_raw(jsonb,jsonb,boolean) from public;
grant execute on function public.merge_worker_raw(jsonb,jsonb,boolean) to service_role;

-- Fence the lead write and its checkpoint in the same transaction. Repeating a
-- sync is safe, and no sales status/ownership/contact mutation is included.
create or replace function public.persist_search_lead(
 p_job_id bigint,p_owner text,p_item_key text,p_stage text,p_row jsonb,p_payload jsonb,p_error jsonb
)
returns bigint language plpgsql security definer set search_path=public as $$
declare item public.leads; saved_id bigint;
begin
 perform 1 from public.admin_search_jobs where id=p_job_id and status='running'
   and lease_owner=p_owner and lease_until>now() for update;
 if not found then return null; end if;
 item := jsonb_populate_record(null::public.leads,p_row);
 insert into public.leads (external_id,name,sector,city,category,phone,address,rating,review_count,maps_url,
   website_url,instagram_url,score,grade,estimated_value_tl,sales_priority_score,next_action,priority_reason,
   recommended_package,matched_services,data_quality,research_brief,ai_report,ai_email,last_analyzed,raw,updated_at)
 values(item.external_id,item.name,item.sector,item.city,item.category,item.phone,item.address,item.rating,
   item.review_count,item.maps_url,item.website_url,item.instagram_url,item.score,item.grade,item.estimated_value_tl,
   item.sales_priority_score,item.next_action,item.priority_reason,item.recommended_package,item.matched_services,
   item.data_quality,item.research_brief,item.ai_report,item.ai_email,item.last_analyzed,item.raw,now())
 on conflict(name) do update set external_id=excluded.external_id,sector=excluded.sector,city=excluded.city,
   category=excluded.category,phone=excluded.phone,address=excluded.address,rating=excluded.rating,
   review_count=excluded.review_count,maps_url=excluded.maps_url,website_url=excluded.website_url,
   instagram_url=excluded.instagram_url,score=excluded.score,grade=excluded.grade,
   estimated_value_tl=excluded.estimated_value_tl,sales_priority_score=excluded.sales_priority_score,
   next_action=excluded.next_action,priority_reason=excluded.priority_reason,recommended_package=excluded.recommended_package,
   matched_services=excluded.matched_services,data_quality=excluded.data_quality,research_brief=case when p_stage='audited' then leads.research_brief else excluded.research_brief end,
   ai_report=case when p_stage='audited' then leads.ai_report else excluded.ai_report end,
   ai_email=case when p_stage='audited' then leads.ai_email else excluded.ai_email end,
   last_analyzed=coalesce(excluded.last_analyzed,leads.last_analyzed),raw=public.merge_worker_raw(leads.raw,excluded.raw,p_stage='audited'),updated_at=now()
 returning id into saved_id;
 perform public.checkpoint_search_job(p_job_id,p_owner,p_item_key,p_stage,
   p_payload||jsonb_build_object('lead_id',saved_id),saved_id,p_error);
 return saved_id;
end;
$$;
revoke all on function public.persist_search_lead(bigint,text,text,text,jsonb,jsonb,jsonb) from public;
grant execute on function public.persist_search_lead(bigint,text,text,text,jsonb,jsonb,jsonb) to service_role;

create or replace function public.search_worker_summary()
returns jsonb language sql stable security definer set search_path=public as $$
 select jsonb_build_object(
   'queued',count(*) filter(where status='queued'),
   'retry_wait',count(*) filter(where status='retry_wait'),
   'running',count(*) filter(where status='running'),
   'stalled',count(*) filter(where status='running' and lease_until<=now()),
   'oldest_queue_seconds',coalesce(extract(epoch from now()-min(created_at) filter(where status='queued')),0),
   'failed_generations',(select count(*) from public.ai_generations where status='failed'),
   'provider_errors_24h',(select count(*) from public.ai_token_ledger where kind='usage' and outcome in ('error','empty') and created_at>=now()-interval '1 day')
 ) from public.admin_search_jobs;
$$;
revoke all on function public.search_worker_summary() from public;
grant execute on function public.search_worker_summary() to service_role;
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
      'worker_stage', to_regprocedure('public.set_search_job_stage(bigint,text,text)') is not null,
      'worker_heartbeat', to_regprocedure('public.heartbeat_search_job(bigint,text)') is not null,
      'worker_finish', to_regprocedure('public.finish_search_job(bigint,text,jsonb,jsonb)') is not null,
      'worker_control', to_regprocedure('public.control_search_job(bigint,text)') is not null,
      'worker_generation', to_regprocedure('public.claim_worker_ai_generation(bigint,text,text,text,text,integer,text,text,bigint,text,text,text)') is not null,
      'owned_generation_completion', to_regprocedure('public.complete_owned_ai_generation(text,text,text,text,text,jsonb)') is not null,
      'worker_claim', to_regprocedure('public.claim_search_job(text)') is not null,
      'worker_checkpoint', to_regprocedure('public.checkpoint_search_job(bigint,text,text,text,jsonb,bigint,jsonb)') is not null,
      'worker_persistence', to_regprocedure('public.persist_search_lead(bigint,text,text,text,jsonb,jsonb,jsonb)') is not null,
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
      'lead_sources', to_regclass('public.lead_sources') is not null,
      'claim_ai_generation', to_regprocedure('public.claim_ai_generation(text,text,text,integer,text,text,bigint,text,text,text)') is not null,
      'ai_spend_summary', to_regprocedure('public.ai_spend_summary(timestamptz)') is not null,
      'ai_model_rates', to_regclass('public.ai_model_rates') is not null,
      'usage_ledger_columns', exists (
        select 1 from information_schema.columns
        where table_schema = 'public' and table_name = 'ai_token_ledger' and column_name = 'cached_tokens'
      )
    )
  );
$$;


create or replace function public.set_search_job_stage(p_job_id bigint,p_owner text,p_stage text)
returns boolean language plpgsql security definer set search_path=public as $$
begin
 update public.admin_search_jobs set progress_stage=p_stage,updated_at=now()
 where id=p_job_id and status='running' and lease_owner=p_owner and lease_until>now();
 return found;
end;
$$;
revoke all on function public.set_search_job_stage(bigint,text,text) from public;
grant execute on function public.set_search_job_stage(bigint,text,text) to service_role;

create or replace function public.ai_spend_summary(p_today_start timestamptz default null)
returns jsonb
language sql
stable
security definer
set search_path = public
as $$
  with usage_rows as (
    select * from public.ai_token_ledger where kind = 'usage'
  ),
  -- A reservation is open while its job is queued or running and has no
  -- release row; jobs finished before 011 have no release row but are closed.
  reservations as (
    select ledger.job_id,
           sum(ledger.estimated_tokens) filter (where ledger.kind = 'reservation') as reserved_tokens,
           sum(ledger.estimated_cost_usd) filter (where ledger.kind = 'reservation') as reserved_usd,
           bool_or(ledger.kind = 'release')
             or coalesce(max(job.status) not in ('queued', 'running', 'retry_wait'), true) as released
    from public.ai_token_ledger ledger
    left join public.admin_search_jobs job on job.id = ledger.job_id
    where ledger.kind in ('reservation', 'release')
    group by ledger.job_id
  )
  select jsonb_build_object(
    'actual_cost_usd', coalesce((select round(sum(actual_cost_usd), 6) from usage_rows), 0),
    'actual_tokens', coalesce((select sum(actual_tokens) from usage_rows), 0),
    'provider_calls', (select count(*) from usage_rows where coalesce(outcome, 'success') <> 'cache_hit'),
    'cache_hits', (select count(*) from usage_rows where outcome = 'cache_hit'),
    'failed_calls', (select count(*) from usage_rows where outcome in ('error', 'empty')),
    'unpriced_calls', (select count(*) from usage_rows where actual_tokens > 0 and actual_cost_usd is null),
    'today_cost_usd', coalesce((
      select round(sum(actual_cost_usd), 6) from usage_rows
      where p_today_start is not null and created_at >= p_today_start
    ), 0),
    'active_reserved_tokens', coalesce((select sum(reserved_tokens) from reservations where not released), 0),
    'active_reserved_usd', coalesce((select round(sum(reserved_usd), 6) from reservations where not released), 0),
    'estimated_cost_usd', coalesce((select round(sum(reserved_usd), 6) from reservations), 0),
    'estimated_tokens', coalesce((select sum(reserved_tokens) from reservations), 0),
    'by_task', coalesce((
      select jsonb_object_agg(task_name, totals) from (
        select coalesce(task, 'unknown') as task_name,
               jsonb_build_object('calls', count(*), 'tokens', coalesce(sum(actual_tokens), 0),
                                  'cost_usd', coalesce(round(sum(actual_cost_usd), 6), 0)) as totals
        from usage_rows where coalesce(outcome, 'success') <> 'cache_hit'
        group by 1
      ) grouped
    ), '{}'::jsonb),
    'by_model', coalesce((
      select jsonb_object_agg(model_name, totals) from (
        select coalesce(model, 'unknown') as model_name,
               jsonb_build_object('calls', count(*), 'tokens', coalesce(sum(actual_tokens), 0),
                                  'cost_usd', coalesce(round(sum(actual_cost_usd), 6), 0)) as totals
        from usage_rows where coalesce(outcome, 'success') <> 'cache_hit'
        group by 1
      ) grouped
    ), '{}'::jsonb)
  );
$$;


insert into public.schema_migrations(version) values('012') on conflict do nothing;
