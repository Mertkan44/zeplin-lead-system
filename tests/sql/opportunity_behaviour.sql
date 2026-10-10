begin;
insert into public.app_users(email,name,role,password_hash)
values ('opp-sales@example.com','Demo Sales','sales','x'),('opp-other@example.com','Demo Other','sales','x');
insert into public.leads(name,city,external_id,status,raw)
values ('Demo Pipeline','Bursa','test:pipeline','yeni','{}'),('Demo Contact Pipeline','Bursa','test:contact-pipeline','yeni','{}'),
       ('Demo Historic Closed','Bursa','test:historic-closed','converted','{}');
select public.assign_lead_owner('Demo Pipeline','opp-sales@example.com','2026-10-11T07:00Z','admin@example.com','active','{}');
select public.assign_lead_owner('Demo Contact Pipeline','opp-sales@example.com',null,'admin@example.com','active','{}');

create function pg_temp.move(key text,actor text,admin boolean,lead text,stage text,note text,amount numeric,unknown boolean)
returns jsonb language sql as $$
 select public.change_opportunity_stage(key,'hash:'||key,actor,admin,l.id,l.revision,
   coalesce((select revision from public.opportunities where lead_id=l.id),0),stage,note,amount,unknown,'web-tasarim')
 from public.leads l where l.name=lead;
$$;

do $$
declare first jsonb; closed jsonb; replay jsonb; lid bigint; oid bigint; old_rev integer;
 count_before integer; actor_rev integer; failed boolean;
begin
 assert not exists(select 1 from public.opportunities), 'existing leads are not reclassified';
 first:=pg_temp.move('10000000-0000-4000-8000-000000000001','opp-sales@example.com',false,'Demo Pipeline','new','',null,true);
 lid:=(first->'opportunity'->>'lead_id')::bigint; oid:=(first->'opportunity'->>'id')::bigint;
 assert (first->'opportunity'->>'revision')::integer=1,'creation has a history revision';
 assert (select count(*) from public.opportunity_history where opportunity_id=oid)=1,'one initial history';
 assert (select count(*) from public.outreach_events where lead_id=lid and action='contact_result_recorded')=0,'creation never invents contact';

 perform pg_temp.move('10000000-0000-4000-8000-000000000002','opp-sales@example.com',false,'Demo Pipeline','discovery','Needs confirmed',12000,false);
 assert (select stage from public.opportunities where id=oid)='discovery','commercial stage persists';
 assert (select amount from public.opportunities where id=oid)=12000,'only actual amount stored';
 begin
   perform pg_temp.move('10000000-0000-4000-8000-000000000003','opp-sales@example.com',false,'Demo Pipeline','new','',null,true);
   failed:=false;
 exception when sqlstate 'PT400' then failed:=true; end;
 assert failed,'backwards transition needs reason';
 assert (select stage from public.opportunities where id=oid)='discovery','rejected transition preserves stage';
 begin
   perform pg_temp.move('10000000-0000-4000-8000-000000000004','opp-other@example.com',false,'Demo Pipeline','proposal','',null,true);
   failed:=false;
 exception when sqlstate 'PT403' then failed:=true; end;
 assert failed,'not-owner is refused';
 begin
   perform public.change_opportunity_stage('10000000-0000-4000-8000-000000000005','stale','opp-sales@example.com',false,lid,0,2,'proposal','',null,true,null);
   failed:=false;
 exception when sqlstate 'PT409' then failed:=true; end;
 assert failed,'stale lead revision is refused';
 old_rev:=(select revision from public.leads where id=lid);
 begin
   perform public.change_opportunity_stage('10000000-0000-4000-8000-000000000006','stale-opp','opp-sales@example.com',false,lid,old_rev,0,'proposal','',null,true,null);
   failed:=false;
 exception when sqlstate 'PT409' then failed:=true; end;
 assert failed,'stale opportunity revision is refused';
 begin
   perform pg_temp.move('10000000-0000-4000-8000-000000000007','opp-sales@example.com',false,'Demo Pipeline','lost','',null,true);
   failed:=false;
 exception when sqlstate 'PT400' then failed:=true; end;
 assert failed,'loss reason required';

 closed:=pg_temp.move('10000000-0000-4000-8000-000000000008','opp-sales@example.com',false,'Demo Pipeline','won','Confirmed',null,true);
 assert (closed->'opportunity'->>'amount_unknown')::boolean,'unknown won amount is explicit';
 assert (select status from public.leads where id=lid)='converted','win closes CRM status';
 assert not exists(select 1 from public.lead_assignments where lead_id=lid and status='active'),'win closes tasks';
 replay:=public.change_opportunity_stage('10000000-0000-4000-8000-000000000008','hash:10000000-0000-4000-8000-000000000008',
   'opp-sales@example.com',false,lid,old_rev,2,'won','Confirmed',null,true,'web-tasarim');
 assert (replay->>'replayed')::boolean,'owner can replay committed close after assignment completes';
 assert (select count(*) from public.opportunity_history where opportunity_id=oid)=3,'retry never duplicates history';
 perform pg_temp.move('10000000-0000-4000-8000-000000000010','admin@example.com',true,'Demo Pipeline','won','Amount confirmed',45000,false);
 assert (select stage from public.opportunities where id=oid)='won','amount edit does not reopen a won opportunity';
 assert (select amount from public.opportunities where id=oid)=45000,'unknown amount can be completed later';
 assert (select count(*) from public.outreach_events where lead_id=lid and action='opportunity_stage_changed' and outcome='won')=1,'amount edit does not count another win';
 begin
   perform public.change_opportunity_stage('10000000-0000-4000-8000-000000000008','changed','opp-sales@example.com',false,lid,old_rev,2,'won','Changed',null,true,'web-tasarim');
   failed:=false;
 exception when sqlstate 'PT409' then failed:=true; end;
 assert failed,'same key different payload is refused';
 begin
   update public.leads set status='contacted' where id=lid;
   failed:=false;
 exception when sqlstate 'PT409' then failed:=true; end;
 assert failed,'legacy status cannot silently reopen opportunity';
 perform pg_temp.move('10000000-0000-4000-8000-000000000009','admin@example.com',true,'Demo Pipeline','new','Customer reconsidered',null,true);
 assert (select closed_at from public.opportunities where id=oid) is null,'reopen is auditable and clears close date';
 assert (select count(*) from public.opportunity_history where opportunity_id=oid)=5,'reopen leaves history';
 assert not exists(select 1 from public.lead_assignments where lead_id=lid and status='active'),'reopen does not invent assignment';
 perform public.assign_lead_owner('Demo Pipeline','opp-other@example.com',null,'admin@example.com','active','{}');
 assert jsonb_array_length(public.list_opportunities('opp-sales@example.com',false))=0,'handover excludes old owner';
 assert jsonb_array_length(public.read_opportunity_history('opp-sales@example.com',false,lid,null,50))=0,'history follows read scope';
 begin
   perform public.change_opportunity_stage('10000000-0000-4000-8000-000000000008','hash:10000000-0000-4000-8000-000000000008',
      'opp-sales@example.com',false,lid,old_rev,2,'won','Confirmed',null,true,'web-tasarim');
   failed:=false;
 exception when sqlstate 'PT403' then failed:=true; end;
 assert failed,'replay after handover cannot leak';
end $$;

-- Contacts use the shared transition; repeated calls do not reduce a commercial stage.
do $$
declare lid bigint; oid bigint; answer jsonb; failed boolean; before_rows integer; rev integer;
begin
 select id into lid from public.leads where name='Demo Contact Pipeline';
 answer:=public.record_contact_result('20000000-0000-4000-8000-000000000001','c1','opp-sales@example.com',false,
 'Demo Contact Pipeline',0,'phone','no_answer','2026-10-11T07:00Z',array['web-tasarim'],null,'Synthetic note','follow_up','active');
 select id into oid from public.opportunities where lead_id=lid;
 assert (select stage from public.opportunities where id=oid)='contact','attempted contact enters commercial stage';
 perform public.record_contact_result('20000000-0000-4000-8000-000000000001','c1','opp-sales@example.com',false,
 'Demo Contact Pipeline',0,'phone','no_answer','2026-10-11T07:00Z',array['web-tasarim'],null,'Synthetic note','follow_up','active');
 assert (select count(*) from public.opportunity_history where opportunity_id=oid)=1,'contact replay writes no second transition';
 perform pg_temp.move('20000000-0000-4000-8000-000000000002','opp-sales@example.com',false,'Demo Contact Pipeline','proposal','Actual proposal',25000,false);
 select revision into rev from public.leads where id=lid;
 perform public.record_contact_result('20000000-0000-4000-8000-000000000003','c2','opp-sales@example.com',false,
 'Demo Contact Pipeline',rev,'phone','no_answer','2026-10-12T07:00Z',array['web-tasarim'],null,'Synthetic note','follow_up','active');
 assert (select stage from public.opportunities where id=oid)='proposal','new missed call does not reduce proposal to contact';
 perform pg_temp.move('20000000-0000-4000-8000-000000000004','opp-sales@example.com',false,'Demo Contact Pipeline','lost','Budget unavailable',null,true);
 assert (select latest_follow_up_at from public.lead_activity_state where lead_id=lid) is null,'loss cancels latest follow-up';
 perform pg_temp.move('20000000-0000-4000-8000-000000000005','admin@example.com',true,'Demo Contact Pipeline','new','Retry agreed',null,true);
 insert into public.outreach_events(lead_name,action,note) values('Demo Contact Pipeline','note_added','Synthetic note after reopen');
 assert (select latest_follow_up_at from public.lead_activity_state where lead_id=lid) is null,'later note cannot resurrect cancelled follow-up';
 perform public.assign_lead_owner('Demo Contact Pipeline','opp-sales@example.com',null,'admin@example.com','active','{}');
 select revision into rev from public.leads where id=lid;
 perform public.record_contact_result('20000000-0000-4000-8000-000000000006','c3','opp-sales@example.com',false,
 'Demo Contact Pipeline',rev,'phone','reached_later','2026-10-13T07:00Z',array['web-tasarim'],null,'Synthetic new contact','follow_up','active');
 assert (select latest_follow_up_at from public.lead_activity_state where lead_id=lid)='2026-10-13T07:00Z'::timestamptz,'new contact after reopen can create follow-up';
 select revision into rev from public.leads where id=lid;
 perform public.record_contact_result('20000000-0000-4000-8000-000000000007','c4','opp-sales@example.com',false,
 'Demo Contact Pipeline',rev,'phone','won',null,array['web-tasarim'],null,'Synthetic win','converted','done');
 assert (select stage from public.opportunities where id=oid)='won','contact win closes same opportunity';
 assert not exists(select 1 from public.opportunities where lead_id=(select id from public.leads where name='Demo Historic Closed')),'historic closure is not fabricated';
 assert not has_function_privilege('service_role','public.apply_opportunity_transition(bigint,text,text,text,text,numeric,boolean,text,integer)','EXECUTE'),'private helper is not callable';
 assert not has_table_privilege('service_role','public.opportunity_history','UPDATE'),'history is append-only for app';
 assert not has_function_privilege('anon','public.list_opportunities(text,boolean)','EXECUTE'),'anon cannot read pipeline';
end $$;

-- A history persistence failure rolls back the lead, opportunity, task and command.
create function pg_temp.fail_history() returns trigger language plpgsql as $$begin raise exception 'synthetic history failure'; end;$$;
create trigger test_fail_history before insert on public.opportunity_history for each row execute function pg_temp.fail_history();
do $$
declare failed boolean; old_stage text; old_revision integer; lid bigint;
begin
 select id,revision into lid,old_revision from public.leads where name='Demo Pipeline';
 select stage into old_stage from public.opportunities where lead_id=lid;
 begin
   perform pg_temp.move('30000000-0000-4000-8000-000000000001','opp-other@example.com',false,'Demo Pipeline','won','',1000,false);
   failed:=false;
 exception when raise_exception then failed:=true; end;
 assert failed,'history error aborts command';
 assert (select stage from public.opportunities where lead_id=lid)=old_stage,'opportunity rolled back';
 assert (select revision from public.leads where id=lid)=old_revision,'lead rolled back';
 assert exists(select 1 from public.lead_assignments where lead_id=lid and status='active'),'task not closed';
 assert not exists(select 1 from public.command_requests where idempotency_key='30000000-0000-4000-8000-000000000001'),'failed command has no replay record';
end $$;
rollback;
