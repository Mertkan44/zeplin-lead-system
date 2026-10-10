begin;
insert into public.app_users(email,name,role,password_hash) values
 ('team-admin@example.com','Demo Admin','admin','synthetic-admin'),
 ('team-second@example.com','Demo Second','admin','synthetic-second'),
 ('team-sales@example.com','Demo Sales','sales','synthetic-sales');

do $$
declare first_result jsonb; retry_result jsonb; failed boolean;
begin
 first_result:=public.manage_team_user('team-admin@example.com','41000000-0000-4000-8000-000000000010','create-hash',true,'team-new@example.com',null,'Demo New','sales',true,null,null,'synthetic-new-hash');
 retry_result:=public.manage_team_user('team-admin@example.com','41000000-0000-4000-8000-000000000010','create-hash',true,'team-new@example.com',null,'Demo New','sales',true,null,null,'synthetic-different-salt');
 assert (retry_result->>'replayed')::boolean,'create retry returns committed result';
 assert (select count(*) from public.audit_events where target_key='team-new@example.com' and event_type='user_created')=1,'create audit occurs once';
 assert not ((first_result->'user')?'password_hash'),'new account response hides hash';
 assert (select password_hash from public.app_users where email='team-new@example.com')='synthetic-new-hash','retry never resets password';
 begin
   perform public.manage_team_user('team-admin@example.com','41000000-0000-4000-8000-000000000011','different-create',true,'team-new@example.com',null,'Overwrite','admin',false,null,null,'different-hash');
   failed:=false;
 exception when sqlstate 'PT409' then failed:=true; end;
 assert failed,'duplicate email cannot silently overwrite account';
 assert (select name='Demo New' and role='sales' and active from public.app_users where email='team-new@example.com'),'duplicate create retains fields';
end $$;

create function pg_temp.manage(key text,actor text,email text,role text,active boolean,expected timestamptz default null)
returns jsonb language sql as $$
 select public.manage_team_user(actor,key,'hash:'||key,false,email,
   coalesce(expected,(select updated_at from public.app_users where app_users.email=manage.email)),
   'Demo User',role,active,'Sales',null,null);
$$;

do $$
declare result jsonb; replay jsonb; failed boolean; old_version timestamptz; old_hash text;
begin
 old_version:=(select updated_at from public.app_users where email='team-sales@example.com');
 result:=pg_temp.manage('41000000-0000-4000-8000-000000000001','team-admin@example.com','team-sales@example.com','admin',false);
 assert (select role='admin' and not active from public.app_users where email='team-sales@example.com'),'role and active change together';
 assert (select password_hash from public.app_users where email='team-sales@example.com')='synthetic-sales','omitted password retained';
 assert not ((result->'user')?'password_hash'),'response never contains password hash';
 assert (select updated_at from public.app_users where email='team-sales@example.com')>old_version,'session version advances';
 replay:=pg_temp.manage('41000000-0000-4000-8000-000000000001','team-admin@example.com','team-sales@example.com','admin',false,old_version);
 assert (replay->>'replayed')::boolean,'retry has one committed result';
 assert (select count(*) from public.audit_events where event_type='user_updated' and target_key='team-sales@example.com')=1,'retry never duplicates audit';
 begin
   perform pg_temp.manage('41000000-0000-4000-8000-000000000002','team-admin@example.com','team-sales@example.com','sales',true,old_version);
   failed:=false;
 exception when sqlstate 'PT409' then failed:=true; end;
 assert failed,'stale form refused';
 begin
   perform pg_temp.manage('41000000-0000-4000-8000-000000000003','team-sales@example.com','team-second@example.com','sales',false);
   failed:=false;
 exception when sqlstate 'PT403' then failed:=true; end;
 assert failed,'inactive user cannot manage others';
 perform pg_temp.manage('41000000-0000-4000-8000-000000000004','team-admin@example.com','team-second@example.com','sales',false);
 begin
   perform pg_temp.manage('41000000-0000-4000-8000-000000000005','team-admin@example.com','team-admin@example.com','sales',true);
   failed:=false;
 exception when sqlstate 'PT409' then failed:=true; end;
 assert failed,'last active admin cannot demote itself';
 assert (select role='admin' and active from public.app_users where email='team-admin@example.com'),'failed demotion leaves admin active';
 begin
   update public.app_users set active=false where email='team-admin@example.com';
   failed:=false;
 exception when sqlstate 'PT409' then failed:=true; end;
 assert failed,'legacy direct writer cannot disable last admin';
 begin
   delete from public.app_users where email='team-admin@example.com';
   failed:=false;
 exception when sqlstate 'PT409' then failed:=true; end;
 assert failed,'last admin cannot be deleted';
 assert not exists(select 1 from public.command_requests where idempotency_key='41000000-0000-4000-8000-000000000005'),'failure has no replay record';
 old_version:=(select updated_at from public.app_users where email='team-second@example.com');
 old_hash:=(select password_hash from public.app_users where email='team-second@example.com');
 begin
   perform public.change_own_password('team-second@example.com',old_version,old_hash,'new-synthetic');
   failed:=false;
 exception when sqlstate 'PT403' then failed:=true; end;
 assert failed,'inactive account cannot change password';
 perform pg_temp.manage('41000000-0000-4000-8000-000000000006','team-admin@example.com','team-second@example.com','sales',true);
 old_version:=(select updated_at from public.app_users where email='team-second@example.com');
 perform public.change_own_password('team-second@example.com',old_version,old_hash,'new-synthetic');
 assert (select password_hash from public.app_users where email='team-second@example.com')='new-synthetic','self password changes';
 assert (select updated_at from public.app_users where email='team-second@example.com')>old_version,'all old sessions invalidated';
 begin
   perform public.change_own_password('team-second@example.com',old_version,old_hash,'another-synthetic');
   failed:=false;
 exception when sqlstate 'PT409' then failed:=true; end;
 assert failed,'concurrent reset cannot be overwritten';
 assert not has_function_privilege('anon','public.manage_team_user(text,text,text,boolean,text,timestamptz,text,text,boolean,text,text,text)','EXECUTE'),'anonymous management forbidden';
 assert not (public.team_management_state('team-admin@example.com')::text like '%synthetic-admin%'),'list hides credentials';
 begin
   perform public.team_management_state('team-second@example.com');failed:=false;
 exception when sqlstate 'PT403' then failed:=true;end;
 assert failed,'sales cannot list full team management';
end $$;

create function pg_temp.fail_user_audit() returns trigger language plpgsql as $$begin raise exception 'synthetic audit failure';end;$$;
create trigger test_fail_user_audit before insert on public.audit_events for each row execute function pg_temp.fail_user_audit();
do $$
declare failed boolean; before_version timestamptz;
begin
 before_version:=(select updated_at from public.app_users where email='team-second@example.com');
 begin
   perform pg_temp.manage('41000000-0000-4000-8000-000000000007','team-admin@example.com','team-second@example.com','admin',false);
   failed:=false;
 exception when raise_exception then failed:=true;end;
 assert failed,'audit failure aborts account command';
 assert (select role='sales' and active and updated_at=before_version from public.app_users where email='team-second@example.com'),'all account fields rolled back';
end $$;
rollback;
