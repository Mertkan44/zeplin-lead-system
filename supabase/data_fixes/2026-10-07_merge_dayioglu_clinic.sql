-- One-off, atomic and repeatable data fix. Apply only after a verified backup.
-- Keeps every assignment/event/generation/ledger/source row and opportunity history.
-- Conflicting owners/opportunities, overlapping assignment history or a worker
-- checkpoint require a human decision; no history is silently discarded.
do $$
declare
 keep_name constant text := 'Kadikoy Dayıoğlu Dental Clinic';
 drop_name constant text := 'Kadıköy Dayıoğlu Diş Polikliniği / Tandarts Reis Turkije';
 kept public.leads; dropped public.leads;
 status_rank constant text[] := array['yeni','ready','missing_info','contacted','follow_up','lost','converted'];
 moved_events integer; moved_assignments integer; moved_opportunities integer;
begin
 perform pg_advisory_xact_lock(hashtext('zeplin:merge:dayioglu:v2'));
 -- All CRM commands lock the parent lead; deterministic order avoids deadlocks.
 perform 1 from public.leads where name in (keep_name,drop_name) order by id for update;
 select * into kept from public.leads where name=keep_name;
 select * into dropped from public.leads where name=drop_name;
 if dropped.id is null and kept.id is not null and exists(
   select 1 from public.audit_events where event_type='lead_merged' and target_key=keep_name
   and meta->>'fix_version'='dayioglu_v2' and meta->>'merged_name'=drop_name) then
   return; -- Already applied: no new writes or duplicate audit.
 end if;
 if kept.id is null or dropped.id is null then raise exception 'CLINIC_MERGE_MISSING_LEAD'; end if;
 if exists(select 1 from pg_constraint c join pg_attribute a
   on a.attrelid=c.conrelid and a.attnum=any(c.conkey)
   where c.confrelid='public.leads'::regclass and
   (c.conrelid not in('public.lead_activity_state'::regclass,'public.ai_generations'::regclass,
      'public.outreach_events'::regclass,'public.lead_assignments'::regclass,'public.lead_sources'::regclass,
      'public.ai_token_ledger'::regclass,'public.admin_search_checkpoints'::regclass,'public.opportunities'::regclass)
    or a.attname not in('lead_id','lead_name'))) then
   raise exception 'CLINIC_MERGE_UNSUPPORTED_REFERENCE';
 end if;
 if public.lead_google_place_id(kept.maps_url,kept.raw) is distinct from 'ChIJMUdXw2e4yhQRxhm2U8e5mlc'
    or public.lead_google_place_id(dropped.maps_url,dropped.raw) is distinct from 'ChIJMUdXw2e4yhQRxhm2U8e5mlc'
    or nullif(kept.phone,'') is null or kept.phone is distinct from dropped.phone
    or nullif(kept.website_url,'') is null or kept.website_url is distinct from dropped.website_url then
   raise exception 'CLINIC_MERGE_IDENTITY_MISMATCH';
 end if;
 if exists(select 1 from public.lead_assignments where lead_id=kept.id and status<>'archived')
    and exists(select 1 from public.lead_assignments where lead_id=dropped.id and status<>'archived') then
   raise exception 'CLINIC_MERGE_OWNER_CONFLICT';
 end if;
 if exists(select 1 from public.lead_assignments a join public.lead_assignments b using(user_email)
           where a.lead_id=kept.id and b.lead_id=dropped.id) then
   raise exception 'CLINIC_MERGE_ASSIGNMENT_HISTORY_CONFLICT';
 end if;
 if (select count(*) from public.opportunities where lead_id in(kept.id,dropped.id))>1 then
   raise exception 'CLINIC_MERGE_OPPORTUNITY_CONFLICT';
 end if;
 if exists(select 1 from public.admin_search_checkpoints where lead_id in(kept.id,dropped.id)) then
   raise exception 'CLINIC_MERGE_WORKER_CHECKPOINT_PRESENT';
 end if;
 -- Preserve opportunity id, revision, amounts, actor and append-only history.
 update public.opportunities set lead_id=kept.id where lead_id=dropped.id;
 get diagnostics moved_opportunities=row_count;
 update public.lead_assignments set lead_name=keep_name,lead_id=kept.id,updated_at=now() where lead_id=dropped.id;
 get diagnostics moved_assignments=row_count;
 update public.outreach_events set lead_name=keep_name,lead_id=kept.id where lead_id=dropped.id;
 get diagnostics moved_events=row_count;
 update public.ai_generations set lead_id=kept.id where lead_id=dropped.id;
 update public.ai_token_ledger set lead_id=kept.id where lead_id=dropped.id;
 update public.lead_sources set lead_id=kept.id where lead_id=dropped.id;
 update public.leads set status=case when array_position(status_rank,dropped.status)>array_position(status_rank,kept.status)
   then dropped.status else kept.status end,revision=revision+1,raw=raw where id=kept.id;
 perform public.refresh_lead_activity_state(kept.id);
 insert into public.audit_events(actor_email,event_type,target_type,target_key,meta)
 values('data-fix','lead_merged','lead',keep_name,jsonb_build_object(
   'fix_version','dayioglu_v2','merged_name',drop_name,'merged_id',dropped.id,'kept_id',kept.id,
   'moved_events',moved_events,'moved_assignments',moved_assignments,'moved_opportunities',moved_opportunities,
   'status_before',kept.status,'merged_status',dropped.status,'previous_revision',kept.revision));
 delete from public.leads where id=dropped.id;
 if exists(select 1 from public.lead_assignments where lead_id=dropped.id)
    or exists(select 1 from public.outreach_events where lead_id=dropped.id) then
   raise exception 'CLINIC_MERGE_REFERENCE_NOT_MOVED';
 end if;
end $$;
