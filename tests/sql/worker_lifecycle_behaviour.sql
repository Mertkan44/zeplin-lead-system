-- WP12 acceptance checks, entirely synthetic and rolled back.
begin;
create function pg_temp.make_job() returns bigint language sql as $$
 insert into public.admin_search_jobs(query,city,max_results,created_by)
 values('sentetik','Test',1,'admin@example.com') returning id;
$$;
create function pg_temp.worker_claim(key text,owner text,job_id bigint,job_owner text) returns jsonb language sql as $$
 select public.claim_worker_ai_generation(job_id,job_owner,key,'report',owner,300,'fixture','fixture',null,'hash','7','catalog');
$$;
do $$
declare id1 bigint; id2 bigint; claimed public.admin_search_jobs; final_status text; lead_id bigint; result jsonb; row_data jsonb;
begin
 id1:=pg_temp.make_job(); id2:=pg_temp.make_job();
 insert into public.ai_token_ledger(job_id,kind,estimated_tokens,estimated_cost_usd) values(id1,'reservation',1000,1);
 select * into claimed from public.claim_search_job('worker-a');
 assert claimed.id=id1 and claimed.attempt_count=1 and claimed.lease_until>now(), 'claim FIFO and one lease';
 assert (select status='queued' from public.admin_search_jobs where id=id2), 'not started remains queued';
 select * into claimed from public.claim_search_job('worker-b');
 assert claimed.id=id2, 'second worker cannot take live first lease';
 assert not public.heartbeat_search_job(id1,'worker-b'), 'wrong owner cannot extend lease';
 assert public.heartbeat_search_job(id1,'worker-a'), 'live owner can heartbeat';
 assert not public.checkpoint_search_job(id1,'worker-b','one','audited','{}',null,null), 'stale owner cannot save';

 row_data:='{"name":"WP12 sentetik","external_id":"test:wp12","recommended_package":{},"matched_services":[],"data_quality":{},"raw":{"ai_report":null,"ai_email":null,"ai_input_hash":null,"ai_prompt_version":null}}';
 lead_id:=public.persist_search_lead(id1,'worker-a','one','audited',row_data,'{}',null);
 assert lead_id is not null, 'audited lead saved before AI';
 update public.leads set status='converted', ai_report='old report',raw='{"ai_report":"old report","ai_input_hash":"old-hash"}' where id=lead_id;
 perform public.persist_search_lead(id1,'worker-a','one','audited',row_data,'{}',null);
 assert (select status='converted' and ai_report='old report' and raw->>'ai_report'='old report' and raw->>'ai_input_hash'='old-hash' from public.leads where id=lead_id), 'audit retry preserves CRM status and old report';
 assert (select count(*)=1 from public.leads where name='WP12 sentetik'), 'sync retry idempotent';

 final_status:=public.finish_search_job(id1,'worker-a','{}','{"stage":"report","code":"provider_error"}');
 assert final_status='retry_wait', 'partial error not mislabeled as success';
 assert not exists(select 1 from public.ai_token_ledger where job_id=id1 and kind='release'), 'keep reservation during retry';
 assert (public.ai_spend_summary()->>'active_reserved_tokens')::integer=1000, 'retry wait remains reserved in panel';
 update public.admin_search_jobs set next_attempt_at=now()-interval '1 second' where id=id1;
 select * into claimed from public.claim_search_job('worker-c');
 assert claimed.id=id1 and claimed.attempt_count=2, 'eligible retry is bounded and claimed';
 assert (select stage='audited' from public.admin_search_checkpoints where job_id=id1 and item_key='one'), 'checkpoint survives retry';
 assert public.finish_search_job(id1,'worker-a','{}',null)='lease_lost', 'old owner cannot finish new lease';

 -- Simulate hard shutdown in a stage. Resume by a new owner after expiry.
 update public.admin_search_jobs set lease_until=now()-interval '1 second' where id=id1;
 assert not public.heartbeat_search_job(id1,'worker-c'), 'expired owner cannot revive';
 assert public.persist_search_lead(id1,'worker-c','one','synced',row_data,'{}',null) is null, 'expired owner cannot change lead';
 select * into claimed from public.claim_search_job('worker-d');
 assert claimed.id=id1 and claimed.attempt_count=3, 'crash consumes an attempt, checkpoints preserved';
 final_status:=public.finish_search_job(id1,'worker-d','{}','{"stage":"report"}');
 assert final_status='partial_success', 'retry limit exposes partial saved leads';
 assert (select count(*)=1 from public.ai_token_ledger where job_id=id1 and kind='release'), 'terminal release once';
 assert (public.ai_spend_summary()->>'active_reserved_tokens')::integer=0, 'terminal job no longer reserved';
 assert (public.control_search_job(id1,'retry')->>'ok')::boolean=false, 'manual retry cannot reset cap';
 assert not exists(select 1 from public.claim_search_job('worker-e')), 'terminal job cannot be claimed';

 -- Cancel twice, stale worker write denied, release stays unique.
 assert (public.control_search_job(id2,'cancel')->>'ok')::boolean, 'cancel succeeds';
 assert (public.control_search_job(id2,'cancel')->>'ok')::boolean, 'cancel idempotent';
 assert not public.heartbeat_search_job(id2,'worker-b'), 'cancel revokes lease immediately';
 assert public.finish_search_job(id2,'worker-b','{}',null)='lease_lost', 'cancelled job cannot be completed';
 assert (select count(*)=1 from public.ai_token_ledger where job_id=id2 and kind='release'), 'cancel releases once';

 -- A concurrent trusted refresh survives a worker's older research snapshot.
 result:=public.merge_worker_raw(
   '{"research":{"google_places":{"place_id":"verified-new"}}}',
   '{"research":{"google_places":{"place_id":"old"},"website":{"status":"ok"}}}',false);
 assert result#>>'{research,google_places,place_id}'='verified-new', 'worker preserves current trusted Places';
 assert result#>>'{research,website,status}'='ok', 'website research still updated';

 -- Cap a generation across job retries, and fence generation completion.
 id1:=pg_temp.make_job(); select * into claimed from public.claim_search_job('ai-job');
 result:=pg_temp.worker_claim('wp12-generation','ai-a',id1,'ai-job');
 assert result->>'status'='claimed', 'worker generation claimed';
 result:=pg_temp.worker_claim('wp12-generation','ai-b',id1,'ai-job');
 assert result->>'status'='busy', 'concurrent generation waits';
 assert not public.complete_owned_ai_generation('wp12-generation','ai-b','bad','fixture','fixture','{}'), 'wrong generation owner rejected';
 perform public.fail_ai_generation('wp12-generation','ai-a','provider_error');
 perform pg_temp.worker_claim('wp12-generation','ai-b',id1,'ai-job');
 perform public.fail_ai_generation('wp12-generation','ai-b','provider_error');
 perform pg_temp.worker_claim('wp12-generation','ai-c',id1,'ai-job');
 perform public.fail_ai_generation('wp12-generation','ai-c','provider_error');
 result:=pg_temp.worker_claim('wp12-generation','ai-d',id1,'ai-job');
 assert result->>'status'='exhausted', 'three generation attempts maximum';
 assert (select attempts=3 from public.ai_generations where cache_key='wp12-generation'), 'no fourth paid attempt';
 result:=pg_temp.worker_claim('wp12-other','ai-a',id1,'wrong-owner');
 assert result->>'status'='lease_lost', 'lost job cannot start a paid generation';

 -- At the cap a hard crash is made visibly failed, no infinite running state.
 id2:=pg_temp.make_job(); select * into claimed from public.claim_search_job('crash');
 update public.admin_search_jobs set attempt_count=3,lease_until=now()-interval '1 second' where id=id2;
 perform public.claim_search_job('recover');
 assert (select status='failed' and last_error->>'code'='retry_limit' from public.admin_search_jobs where id=id2), 'terminal crash recovered';
 assert (select count(*)=1 from public.ai_token_ledger where job_id=id2 and kind='release'), 'terminal crash reservation released';

 assert not has_function_privilege('anon','public.claim_search_job(text)','execute'), 'anonymous cannot claim';
 assert not has_function_privilege('authenticated','public.control_search_job(bigint,text)','execute'), 'user cannot bypass admin API';
 assert not has_table_privilege('anon','public.admin_search_checkpoints','select'), 'checkpoint data private';
end;
$$;
rollback;
