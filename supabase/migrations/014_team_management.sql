-- One atomic user command; legacy direct writes also keep the last admin.
create or replace function public.protect_last_admin()
returns trigger language plpgsql security definer set search_path='' as $$
begin
 perform pg_advisory_xact_lock(hashtext('zeplin:team-management'));
 if old.active and old.role='admin'
    and (tg_op='DELETE' or not new.active or new.role<>'admin')
    and not exists(select 1 from public.app_users where active and role='admin' and id<>old.id for update) then
   raise exception using errcode='PT409',message='LAST_ADMIN_REQUIRED';
 end if;
 if tg_op='DELETE' then return old; end if;
 new.updated_at:=clock_timestamp();
 return new;
end;
$$;
revoke all on function public.protect_last_admin() from public,anon,authenticated,service_role;
create or replace trigger app_users_last_admin before delete on public.app_users
for each row execute function public.protect_last_admin();
-- Replace the old now()-based version trigger; two changes in one transaction
-- must still receive different session/form versions.
create or replace trigger app_users_set_updated_at before update on public.app_users
for each row execute function public.protect_last_admin();

create or replace function public.manage_team_user(
 p_actor text,p_key text,p_hash text,p_create boolean,p_email text,p_expected timestamptz,
 p_name text,p_role text,p_active boolean,p_title text,p_avatar text,p_password_hash text
) returns jsonb language plpgsql security definer set search_path='' as $$
declare target public.app_users; prior public.command_requests; answer jsonb; public_user jsonb;
begin
 -- All writers serialize before locking individual users; re-check the actor
 -- after this lock, so simultaneous self-demotions cannot leave zero admins.
 perform pg_advisory_xact_lock(hashtext('zeplin:team-management'));
 if not exists(select 1 from public.app_users where lower(email)=lower(p_actor) and active and role='admin' for update) then
   raise exception using errcode='PT403',message='TEAM_ADMIN_REQUIRED';
 end if;
 if p_key is null or p_key!~'^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$'
    or nullif(p_hash,'') is null or p_create is null or p_active is null
    or p_role is null or p_role not in ('admin','sales') or nullif(trim(p_email),'') is null
    or nullif(trim(p_name),'') is null or length(p_name)>120 or length(coalesce(p_title,''))>120 or length(coalesce(p_avatar,''))>500 then
   raise exception using errcode='PT400',message='USER_COMMAND_INVALID';
 end if;
 select * into prior from public.command_requests where idempotency_key=p_key;
 if found then
   if prior.command<>'manage_team_user' or prior.actor_email<>lower(p_actor) or prior.request_hash<>p_hash then
     raise exception using errcode='PT409',message='IDEMPOTENCY_KEY_REUSED';
   end if;
   return prior.response||jsonb_build_object('replayed',true);
 end if;
 select * into target from public.app_users where email=lower(p_email) for update;
 if p_create then
   if target.id is not null then raise exception using errcode='PT409',message='USER_ALREADY_EXISTS'; end if;
   if nullif(p_password_hash,'') is null then raise exception using errcode='PT400',message='USER_PASSWORD_REQUIRED'; end if;
   insert into public.app_users(email,name,role,active,title,avatar_url,password_hash)
   values(lower(p_email),p_name,p_role,p_active,nullif(p_title,''),nullif(p_avatar,''),p_password_hash) returning * into target;
 else
   if target.id is null then raise exception using errcode='PT404',message='USER_NOT_FOUND'; end if;
   if p_expected is null or target.updated_at<>p_expected then raise exception using errcode='PT409',message='USER_VERSION_CONFLICT'; end if;
   update public.app_users set name=p_name,role=p_role,active=p_active,title=nullif(p_title,''),avatar_url=nullif(p_avatar,''),
     password_hash=coalesce(nullif(p_password_hash,''),password_hash)
   where id=target.id returning * into target;
 end if;
 public_user:=to_jsonb(target)-'password_hash';
 answer:=jsonb_build_object('user',public_user,'account_changed',lower(p_email)=lower(p_actor));
 insert into public.audit_events(actor_email,event_type,target_type,target_key,meta)
 values(lower(p_actor),case when p_create then 'user_created' else 'user_updated' end,'user',target.email,
   jsonb_build_object('role',target.role,'active',target.active,'password_changed',p_password_hash is not null));
 insert into public.command_requests(idempotency_key,command,actor_email,request_hash,response)
 values(p_key,'manage_team_user',lower(p_actor),p_hash,answer);
 return answer||jsonb_build_object('replayed',false);
end;
$$;
revoke all on function public.manage_team_user(text,text,text,boolean,text,timestamptz,text,text,boolean,text,text,text) from public,anon,authenticated;
grant execute on function public.manage_team_user(text,text,text,boolean,text,timestamptz,text,text,boolean,text,text,text) to service_role;

create or replace function public.change_own_password(p_actor text,p_expected timestamptz,p_previous_hash text,p_new_hash text)
returns jsonb language plpgsql security definer set search_path='' as $$
declare target public.app_users;
begin
 perform pg_advisory_xact_lock(hashtext('zeplin:team-management'));
 select * into target from public.app_users where email=lower(p_actor) and active for update;
 if target.id is null then raise exception using errcode='PT403',message='ACCOUNT_UNAVAILABLE'; end if;
 if p_expected is null or target.updated_at<>p_expected or target.password_hash is distinct from p_previous_hash then
   raise exception using errcode='PT409',message='USER_VERSION_CONFLICT';
 end if;
 if nullif(p_new_hash,'') is null then raise exception using errcode='PT400',message='USER_PASSWORD_REQUIRED'; end if;
 update public.app_users set password_hash=p_new_hash where id=target.id;
 insert into public.audit_events(actor_email,event_type,target_type,target_key,meta)
 values(lower(p_actor),'own_password_changed','user',target.email,'{}');
 return jsonb_build_object('session_ended',true);
end;
$$;
revoke all on function public.change_own_password(text,timestamptz,text,text) from public,anon,authenticated;
grant execute on function public.change_own_password(text,timestamptz,text,text) to service_role;

create or replace function public.team_management_state(p_actor text)
returns jsonb language plpgsql stable security definer set search_path='' as $$
declare answer jsonb;
begin
 if not exists(select 1 from public.app_users where email=lower(p_actor) and active and role='admin') then
   raise exception using errcode='PT403',message='TEAM_ADMIN_REQUIRED';
 end if;
 select coalesce(jsonb_agg((to_jsonb(u)-'password_hash')||jsonb_build_object(
   'active_assignments',coalesce(tasks.total,0),'overdue_assignments',coalesce(tasks.overdue,0)
 ) order by u.name,u.id),'[]') into answer
 from public.app_users u left join lateral(
   select count(*) as total,count(*) filter(where a.due_at<=now()) as overdue
   from public.lead_assignments a where a.user_email=u.email and a.status='active'
 ) tasks on true;
 return answer;
end;
$$;
revoke all on function public.team_management_state(text) from public,anon,authenticated;
grant execute on function public.team_management_state(text) to service_role;

create or replace function public.team_schema_readiness()
returns jsonb language sql stable security definer set search_path='' as $$
 select jsonb_build_object(
 'team_command',to_regprocedure('public.manage_team_user(text,text,text,boolean,text,timestamptz,text,text,boolean,text,text,text)') is not null,
 'own_password_command',to_regprocedure('public.change_own_password(text,timestamptz,text,text)') is not null,
 'team_read',to_regprocedure('public.team_management_state(text)') is not null,
 'last_admin_guard',exists(select 1 from pg_trigger where tgrelid='public.app_users'::regclass and tgname='app_users_last_admin' and tgfoid='public.protect_last_admin()'::regprocedure and tgenabled<>'D'),
 'user_version_guard',exists(select 1 from pg_trigger where tgrelid='public.app_users'::regclass and tgname='app_users_set_updated_at' and tgfoid='public.protect_last_admin()'::regprocedure and tgenabled<>'D'));
$$;
revoke all on function public.team_schema_readiness() from public,anon,authenticated;
grant execute on function public.team_schema_readiness() to service_role;
insert into public.schema_migrations(version) values('014') on conflict do nothing;
