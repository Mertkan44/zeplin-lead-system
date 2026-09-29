-- Keep partial scans distinct from fully successful jobs.
alter table public.admin_search_jobs
  drop constraint if exists admin_search_jobs_status_check;
alter table public.admin_search_jobs
  add constraint admin_search_jobs_status_check
  check (status in ('queued', 'running', 'success', 'partial_success', 'failed'));
