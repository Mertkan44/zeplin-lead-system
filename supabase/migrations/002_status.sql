alter table public.leads
  add column if not exists status text not null default 'yeni'
  check (status in ('yeni', 'contacted', 'converted'));

create index if not exists leads_status_idx on public.leads (status);
