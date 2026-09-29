-- Populate the native fields added in 007 from historical versioned notes.
-- A malformed legacy note is skipped without stopping the migration.
do $$
declare
  item record;
  payload jsonb;
begin
  for item in
    select id, note from public.outreach_events
    where note like 'ZEPLIN_ACTIVITY_V1:%'
       or note like 'ZEPLIN_DRAFT_V1:%'
  loop
    begin
      if item.note like 'ZEPLIN_ACTIVITY_V1:%' then
        payload := substring(item.note from length('ZEPLIN_ACTIVITY_V1:') + 1)::jsonb;
        update public.outreach_events
          set channel = payload->>'channel',
              outcome = payload->>'outcome',
              follow_up_at = nullif(payload->>'follow_up_at', '')::timestamptz,
              service_slugs = coalesce(array(select jsonb_array_elements_text(payload->'service_slugs')), '{}'),
              contact_name = payload->>'contact_name'
          where id = item.id;
      else
        payload := substring(item.note from length('ZEPLIN_DRAFT_V1:') + 1)::jsonb;
        update public.outreach_events
          set channel = payload->>'channel'
          where id = item.id;
      end if;
    exception when others then
      raise notice 'Skipping malformed outreach event %', item.id;
    end;
  end loop;
end;
$$;
