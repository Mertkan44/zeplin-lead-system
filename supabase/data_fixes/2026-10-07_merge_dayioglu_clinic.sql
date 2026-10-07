-- One-off data fix (not a migration): merge a clinic that was stored twice.
--
-- scripts/lead_identity_report.py found two leads with the same Google place
-- id (ChIJMUdXw2e4yhQRxhm2U8e5mlc), phone and website. The English-named row is
-- kept (newer analysis, review count present); the Turkish-named row is merged
-- into it. Its contact history and assignments move to the kept lead, a CRM
-- status further along the pipeline is carried over, then the row is deleted.
--
-- The whole block is atomic: any error leaves the database unchanged. It stops
-- without changing anything if both leads have live assignments, because then
-- a person has to decide who keeps the lead. Running it a second time after a
-- successful run stops at "one of the leads is missing" and changes nothing.
--
-- leads_final.json no longer contains the merged row, so the next sync does
-- not bring it back.

do $$
declare
  keep_name constant text := 'Kadikoy Dayıoğlu Dental Clinic';
  drop_name constant text := 'Kadıköy Dayıoğlu Diş Polikliniği / Tandarts Reis Turkije';
  keep_id bigint;
  drop_id bigint;
  keep_status text;
  drop_status text;
  status_rank constant text[] := array['yeni', 'ready', 'missing_info', 'contacted', 'follow_up', 'lost', 'converted'];
  moved_events integer;
  moved_assignments integer;
begin
  select id, status into keep_id, keep_status from public.leads where name = keep_name;
  select id, status into drop_id, drop_status from public.leads where name = drop_name;
  if keep_id is null or drop_id is null then
    raise exception 'one of the leads is missing (already merged?): keep=%, drop=%', keep_id, drop_id;
  end if;

  if exists (select 1 from public.lead_assignments where lead_name = drop_name and status <> 'archived')
     and exists (select 1 from public.lead_assignments where lead_name = keep_name and status <> 'archived') then
    raise exception 'both leads have live assignments; decide the owner first, nothing was changed';
  end if;

  -- One row per (lead, user): where a user has rows on both leads, keep the
  -- live one, or the kept lead's row when both are archived.
  delete from public.lead_assignments keep_row
  using public.lead_assignments drop_row
  where keep_row.lead_name = keep_name
    and drop_row.lead_name = drop_name
    and drop_row.user_email = keep_row.user_email
    and keep_row.status = 'archived'
    and drop_row.status <> 'archived';
  delete from public.lead_assignments drop_row
  using public.lead_assignments keep_row
  where drop_row.lead_name = drop_name
    and keep_row.lead_name = keep_name
    and keep_row.user_email = drop_row.user_email;

  update public.lead_assignments
  set lead_name = keep_name, lead_id = keep_id, updated_at = now()
  where lead_name = drop_name;
  get diagnostics moved_assignments = row_count;

  update public.outreach_events
  set lead_name = keep_name, lead_id = keep_id
  where lead_name = drop_name;
  get diagnostics moved_events = row_count;

  if array_position(status_rank, drop_status) > array_position(status_rank, keep_status) then
    update public.leads set status = drop_status, updated_at = now() where id = keep_id;
  end if;

  insert into public.audit_events (actor_email, event_type, target_type, target_key, meta)
  values (
    'data-fix', 'lead_merged', 'lead', keep_name,
    jsonb_build_object(
      'merged_name', drop_name, 'merged_id', drop_id, 'kept_id', keep_id,
      'moved_events', moved_events, 'moved_assignments', moved_assignments,
      'status_before', keep_status, 'merged_status', drop_status
    )
  );

  delete from public.leads where id = drop_id;

  -- The place id is no longer shared: record it for the kept lead.
  update public.leads set raw = raw where id = keep_id;

  raise notice 'merged lead % into %: % events, % assignments moved',
    drop_id, keep_id, moved_events, moved_assignments;
end $$;
