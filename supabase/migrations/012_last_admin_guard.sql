-- Enforce the last-active-admin rule in the database as well as in the API.
-- The transaction lock serializes concurrent demotions/deactivations.
create or replace function public.guard_last_active_admin()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
  if tg_op = 'DELETE' then
    if old.role = 'admin' and old.active then
      perform pg_advisory_xact_lock(527994, 1);
      if (select count(*) from public.app_users where role = 'admin' and active) <= 1 then
        raise exception 'the last active admin cannot be removed';
      end if;
    end if;
    return old;
  end if;
  if old.role = 'admin' and old.active
     and (new.role <> 'admin' or not new.active) then
    perform pg_advisory_xact_lock(527994, 1);
    if (select count(*) from public.app_users where role = 'admin' and active) <= 1 then
      raise exception 'the last active admin cannot be removed';
    end if;
  end if;
  return new;
end;
$$;

drop trigger if exists app_users_last_admin_guard on public.app_users;
create trigger app_users_last_admin_guard
before update or delete on public.app_users
for each row execute function public.guard_last_active_admin();
