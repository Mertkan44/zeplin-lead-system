alter table if exists public.app_users
  add column if not exists title text,
  add column if not exists avatar_url text;
