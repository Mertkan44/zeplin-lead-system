-- Official USD tariff verified 2026-10-13; do not rewrite historical usage.
-- https://api-docs.deepseek.com/quick_start/pricing/
alter table public.ai_model_rates add column if not exists off_peak_multiplier numeric
  check (off_peak_multiplier > 0 and off_peak_multiplier <= 1);
alter table public.ai_model_rates add column if not exists pricing_policy text;
do $$ begin
 if not exists(select 1 from pg_constraint where conrelid='public.ai_model_rates'::regclass and conname='ai_model_rates_time_policy') then
   alter table public.ai_model_rates add constraint ai_model_rates_time_policy
   check(pricing_policy is distinct from 'deepseek_peak_2026' or off_peak_multiplier is not null);
 end if;
end $$;
insert into public.ai_model_rates(provider,model,effective_from,input_usd_per_m,cached_input_usd_per_m,output_usd_per_m,off_peak_multiplier,pricing_policy,source_note)
values
 ('deepseek','deepseek-flash','2026-10-13',0.30,0.006,1.20,0.5,'deepseek_peak_2026','https://api-docs.deepseek.com/quick_start/pricing/ verified 2026-10-13; UTC peak, Chinese holidays excluded'),
 ('deepseek','deepseek-v4-flash','2026-10-13',0.30,0.006,1.20,0.5,'deepseek_peak_2026','Official legacy alias served as DeepSeek-V4.1-Flash; https://api-docs.deepseek.com/quick_start/pricing/'),
 ('deepseek','deepseek-v4-flash-vision-exp','2026-10-13',0.30,0.006,1.20,0.5,'deepseek_peak_2026','Official legacy alias served as DeepSeek-V4.1-Flash; https://api-docs.deepseek.com/quick_start/pricing/'),
 ('deepseek','deepseek-v4-pro','2026-10-13',1.32,0.044,3.96,0.5,'deepseek_peak_2026','https://api-docs.deepseek.com/quick_start/pricing/ verified 2026-10-13')
on conflict(provider,model,effective_from) do nothing;

create or replace function public.pricing_schema_readiness()
returns jsonb language sql set search_path=public as $$
 select jsonb_build_object('time_based_pricing',(
   select count(*)=2 from information_schema.columns where table_schema='public'
   and table_name='ai_model_rates' and column_name in ('off_peak_multiplier','pricing_policy')));
$$;
revoke all on function public.pricing_schema_readiness() from public,anon,authenticated;
grant execute on function public.pricing_schema_readiness() to service_role;
insert into public.schema_migrations(version) values ('016') on conflict do nothing;
