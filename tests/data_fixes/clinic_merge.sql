begin;
insert into public.app_users(email,name,role,password_hash)
values('merge-sales@example.com','Demo Sales','sales','synthetic-only'),
      ('merge-other@example.com','Demo Other','sales','synthetic-only');
insert into public.leads(name,city,external_id,phone,website_url,maps_url,raw)
values('Kadikoy Dayıoğlu Dental Clinic','Istanbul','merge:keep','000','https://synthetic.example',
 'https://maps.example/data=!19sChIJMUdXw2e4yhQRxhm2U8e5mlc','{}'),
 ('Kadıköy Dayıoğlu Diş Polikliniği / Tandarts Reis Turkije','Istanbul','merge:drop','000','https://synthetic.example',
 'https://maps.example/data=!19sChIJMUdXw2e4yhQRxhm2U8e5mlc','{}');
select public.assign_lead_owner('Kadıköy Dayıoğlu Diş Polikliniği / Tandarts Reis Turkije',
 'merge-sales@example.com',null,'admin@example.com','active','{}');
select public.record_contact_result('merge-contact-synthetic-01','hash','merge-sales@example.com',false,
 'Kadıköy Dayıoğlu Diş Polikliniği / Tandarts Reis Turkije',0,'phone','reached_later',
 now()+interval '1 day',array[]::text[],null,'Synthetic merge contact','follow_up','active');
insert into public.ai_generations(cache_key,lead_id,task,provider,model,content,status)
select 'merge-synthetic',id,'report','demo','demo','Synthetic report','ready' from public.leads where external_id='merge:drop';
insert into public.ai_token_ledger(kind,lead_id,provider,model,actual_tokens,actual_cost_usd)
select 'usage',id,'demo','demo',10,0.0001 from public.leads where external_id='merge:drop';

do $$
declare keeper bigint; loser bigint; oid bigint; history_before jsonb; original_events integer;
        failed boolean; before_state jsonb; after_state jsonb;
begin
 select id into keeper from public.leads where external_id='merge:keep';
 select id into loser from public.leads where external_id='merge:drop';
 select id into oid from public.opportunities where lead_id=loser;
 select jsonb_agg(to_jsonb(h) order by id) into history_before from public.opportunity_history h where opportunity_id=oid;
 select count(*) into original_events from public.outreach_events;
 -- A conflicting owner aborts before any mutation.
 perform public.assign_lead_owner('Kadikoy Dayıoğlu Dental Clinic','merge-other@example.com',null,'admin@example.com','active','{}');
 begin perform pg_temp.merge_clinic(); failed:=false;
 exception when others then failed:=sqlerrm='CLINIC_MERGE_OWNER_CONFLICT'; end;
 assert failed; assert exists(select 1 from public.leads where id=loser);
 delete from public.lead_assignments where lead_id=keeper;
 -- Two opportunities require an explicit decision; no history gets deleted.
 insert into public.opportunities(lead_id) values(keeper);
 begin perform pg_temp.merge_clinic(); failed:=false;
 exception when others then failed:=sqlerrm='CLINIC_MERGE_OPPORTUNITY_CONFLICT'; end;
 assert failed; assert (select count(*) from public.opportunities where lead_id in(keeper,loser))=2;
 delete from public.opportunities where lead_id=keeper;
 -- Archived overlap also must not silently destroy old assignment history.
 insert into public.lead_assignments(lead_name,lead_id,user_email,status)
 values('Kadikoy Dayıoğlu Dental Clinic',keeper,'merge-sales@example.com','archived');
 begin perform pg_temp.merge_clinic(); failed:=false;
 exception when others then failed:=sqlerrm='CLINIC_MERGE_ASSIGNMENT_HISTORY_CONFLICT'; end;
 assert failed; delete from public.lead_assignments where lead_id=keeper;
 -- Identity disagreement leaves both originals unchanged.
 update public.leads set phone='different' where id=keeper;
 begin perform pg_temp.merge_clinic(); failed:=false;
 exception when others then failed:=sqlerrm='CLINIC_MERGE_IDENTITY_MISMATCH'; end;
 assert failed; update public.leads set phone='000' where id=keeper;
 -- A stored worker checkpoint must not resume with a deleted or renamed lead.
 insert into public.admin_search_jobs(query,city,max_results,deep_research,ai_mode,status,created_by)
 values('Synthetic checkpoint','Istanbul',1,false,'flash','success','admin@example.com');
 insert into public.admin_search_checkpoints(job_id,item_key,stage,lead_id)
 select max(id),'synthetic-key','ready',loser from public.admin_search_jobs;
 begin perform pg_temp.merge_clinic(); failed:=false;
 exception when others then failed:=sqlerrm='CLINIC_MERGE_WORKER_CHECKPOINT_PRESENT'; end;
 assert failed; delete from public.admin_search_checkpoints;
 -- An error after writes began still rolls back every reference movement.
 create function pg_temp.reject_merge_audit() returns trigger language plpgsql as $audit$
 begin
   if new.event_type='lead_merged' then raise exception 'SYNTHETIC_AUDIT_FAILURE'; end if;
   return new;
 end $audit$;
 create trigger reject_merge_audit before insert on public.audit_events
 for each row execute function pg_temp.reject_merge_audit();
 begin perform pg_temp.merge_clinic(); failed:=false;
 exception when others then failed:=sqlerrm='SYNTHETIC_AUDIT_FAILURE'; end;
 assert failed;
 assert exists(select 1 from public.leads where id=loser);
 assert (select lead_id from public.opportunities where id=oid)=loser;
 assert (select lead_id from public.ai_generations where cache_key='merge-synthetic')=loser;
 assert exists(select 1 from public.lead_assignments where lead_id=loser and status='active');
 assert exists(select 1 from public.outreach_events where lead_id=loser);
 drop trigger reject_merge_audit on public.audit_events;
 perform pg_temp.merge_clinic();
 assert not exists(select 1 from public.leads where id=loser);
 assert (select count(*) from public.outreach_events)=original_events;
 assert (select count(*) from public.outreach_events where lead_id=keeper)>0;
 assert exists(select 1 from public.lead_assignments where lead_id=keeper and user_email='merge-sales@example.com' and status='active');
 assert (select lead_id from public.ai_generations where cache_key='merge-synthetic')=keeper;
 assert exists(select 1 from public.ai_token_ledger where lead_id=keeper and actual_cost_usd=0.0001);
 assert (select lead_id from public.opportunities where id=oid)=keeper;
 assert history_before=(select jsonb_agg(to_jsonb(h) order by id) from public.opportunity_history h where opportunity_id=oid);
 assert (select latest_outcome from public.lead_activity_state where lead_id=keeper)='reached_later';
 assert (select revision from public.leads where id=keeper)=1;
 select jsonb_build_object('lead',to_jsonb(l),'audit',(select count(*) from public.audit_events)) into before_state
 from public.leads l where id=keeper;
 perform pg_temp.merge_clinic();
 select jsonb_build_object('lead',to_jsonb(l),'audit',(select count(*) from public.audit_events)) into after_state
 from public.leads l where id=keeper;
 assert before_state=after_state, 'retry must not create another merge or increment revision';
end $$;
rollback;
