-- Apply after 008. Update a limited set of lead fields without replacing the raw record.
create or replace function public.patch_lead_fields(
  target_name text,
  expected_updated_at timestamptz,
  field_patch jsonb
)
returns boolean
language plpgsql
security definer
set search_path = public
as $$
begin
  update public.leads
  set raw = coalesce(raw, '{}'::jsonb) || field_patch,
      ai_report = case when field_patch ? 'ai_report' then field_patch->>'ai_report' else ai_report end,
      ai_email = case when field_patch ? 'ai_email' then field_patch->>'ai_email' else ai_email end,
      research_brief = case when field_patch ? 'research_brief' then field_patch->>'research_brief' else research_brief end,
      last_analyzed = case when field_patch ? 'last_analyzed' then field_patch->>'last_analyzed' else last_analyzed end,
      maps_url = case when field_patch ? 'maps_url' then field_patch->>'maps_url' else maps_url end,
      address = case when field_patch ? 'address' then field_patch->>'address' else address end,
      rating = case when field_patch ? 'rating' then (field_patch->>'rating')::numeric else rating end,
      review_count = case when field_patch ? 'review_count' then (field_patch->>'review_count')::integer else review_count end,
      phone = case when field_patch ? 'phone' then field_patch->>'phone' else phone end,
      website_url = case when field_patch ? 'website' then field_patch->'website'->>'website_url' else website_url end,
      updated_at = now()
  where name = target_name and updated_at = expected_updated_at;
  return found;
end;
$$;

revoke all on function public.patch_lead_fields(text, timestamptz, jsonb)
  from public, anon, authenticated;
grant execute on function public.patch_lead_fields(text, timestamptz, jsonb)
  to service_role;
